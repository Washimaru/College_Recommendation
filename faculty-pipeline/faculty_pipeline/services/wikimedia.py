"""MediaWiki / Wikidata API access.

Why this exists rather than another directory crawl: extracting a professor
from directory prose needs an LLM, and the model can be wrong about whether a
person exists. These two APIs return *structured* answers — "is this page a
human", "what is their date of death", "how many language Wikipedias have an
article" — so a professor is either in the data or is not. Nothing here can
invent one.

## robots.txt, deliberately

`https://en.wikipedia.org/robots.txt` says `Disallow: /w/` for `User-agent: *`,
which covers `/w/api.php`. That rule exists to keep crawlers off expensive
dynamic endpoints while they spider article HTML; the API *is* Wikimedia's
sanctioned route for programmatic access, and its published etiquette asks for
a descriptive User-Agent and serialised requests instead. `ApiRobots` below
encodes that as a narrow, explicit exemption — two hosts, API paths only,
everything else still delegated to the real robots checker — because the rest
of this pipeline refuses robots-disallowed URLs and that behaviour must not be
weakened by a blanket override.

Politeness is not waived, only relocated: requests go through the same
`HttpClient` as every other fetch, so they inherit its per-host rate limit,
on-disk cache and backoff. A burst of ~60 unthrottled requests earns a 429,
which is what this avoids.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Protocol
from urllib.parse import urlencode, urlsplit

WIKIPEDIA_HOST = "en.wikipedia.org"
WIKIDATA_HOST = "www.wikidata.org"
API_HOSTS = (WIKIPEDIA_HOST, WIKIDATA_HOST)
API_PATH = "/w/api.php"

# The API caps a titles/ids query at 50 for anonymous callers.
BATCH = 50

# Wikidata property and item ids used here.
P_INSTANCE_OF = "P31"
P_OCCUPATION = "P106"
P_DATE_OF_DEATH = "P570"
P_AWARD_RECEIVED = "P166"
Q_HUMAN = "Q5"


class RobotsCheckerLike(Protocol):
    def is_allowed(self, url: str, user_agent: str) -> bool: ...
    def crawl_delay(self, url: str) -> float | None: ...
    def sitemaps(self, url: str) -> list[str]: ...


class ApiRobots:
    """Allows the two MediaWiki API endpoints; delegates every other URL.

    Deliberately narrow: an exemption for `en.wikipedia.org/w/api.php` and
    `www.wikidata.org/w/api.php` and nothing else, so this cannot become a way
    to crawl article HTML — or anyone else's site — around a robots rule.
    """

    def __init__(self, inner: RobotsCheckerLike) -> None:
        self._inner = inner

    def _is_api(self, url: str) -> bool:
        parts = urlsplit(url)
        return parts.netloc in API_HOSTS and parts.path == API_PATH

    def is_allowed(self, url: str, user_agent: str) -> bool:
        if self._is_api(url):
            return True
        return self._inner.is_allowed(url, user_agent)

    def crawl_delay(self, url: str) -> float | None:
        return self._inner.crawl_delay(url)

    def sitemaps(self, url: str) -> list[str]:
        return self._inner.sitemaps(url)


class HttpFetcher(Protocol):
    """The subset of `services.http_client.HttpClient` this module needs."""

    def fetch(self, url: str, *, method: str = "GET") -> Any: ...


class MediaWikiError(RuntimeError):
    """The API answered, but with an error or unparseable body."""


class MediaWikiApi:
    """Thin, typed wrapper over the query API."""

    def __init__(self, http: HttpFetcher, logger: logging.Logger | None = None) -> None:
        self._http = http
        self._logger = logger or logging.getLogger(__name__)

    def query(self, host: str, **params: str) -> dict[str, Any]:
        params.setdefault("format", "json")
        # maxlag makes the API shed our load first when replication is behind,
        # which is the documented way to be a good citizen at scale.
        params.setdefault("maxlag", "5")
        url = f"https://{host}{API_PATH}?" + urlencode(params)
        result = self._http.fetch(url)
        try:
            body = json.loads(result.body)
        except json.JSONDecodeError as exc:
            raise MediaWikiError(f"non-JSON response from {host}") from exc
        if isinstance(body, dict) and "error" in body:
            raise MediaWikiError(str(body["error"].get("info", body["error"])))
        return body

    # -- Wikipedia -------------------------------------------------------

    def category_members(self, category: str, *, cap: int = 1500) -> list[str]:
        """Article titles in `category`, following continuations up to `cap`.

        `cmtype=page` already excludes subcategories and files; the caller
        still filters list and template articles, which are pages.
        """
        titles: list[str] = []
        cont: dict[str, str] = {}
        while len(titles) < cap:
            body = self.query(
                WIKIPEDIA_HOST, action="query", list="categorymembers",
                cmtitle=category, cmlimit="500", cmtype="page", **cont,
            )
            titles += [m["title"] for m in body.get("query", {}).get("categorymembers", [])]
            following = body.get("continue")
            if not following:
                break
            cont = {k: v for k, v in following.items() if k != "continue"}
            cont["continue"] = following["continue"]
        return titles[:cap]

    def wikidata_ids(self, titles: list[str]) -> dict[str, str]:
        """Article title -> Wikidata QID, for the titles that have one."""
        found: dict[str, str] = {}
        for chunk in _chunks(titles, BATCH):
            body = self.query(
                WIKIPEDIA_HOST, action="query", prop="pageprops",
                ppprop="wikibase_item", redirects="1", titles="|".join(chunk),
            )
            for page in body.get("query", {}).get("pages", {}).values():
                qid = (page.get("pageprops") or {}).get("wikibase_item")
                if qid:
                    found[page["title"]] = qid
        return found

    def canonical_title(self, name: str) -> str | None:
        """The article title `name` resolves to, following redirects.

        Wikipedia's title is often not the catalog's: "Georgia Institute of
        Technology" redirects to "Georgia Tech", "University of Maryland" to
        "University of Maryland, College Park". Returns None when no article
        exists at all.
        """
        body = self.query(WIKIPEDIA_HOST, action="query", titles=name, redirects="1")
        pages = body.get("query", {}).get("pages", {})
        for page in pages.values():
            if "missing" not in page and page.get("title"):
                return page["title"]
        return None

    def search_article(self, name: str) -> str | None:
        """The article Wikipedia thinks `name` means.

        Needed when the catalog's name is not a title *or* a redirect:
        "Binghamton University (SUNY)" and "United States Military Academy
        (West Point)" are neither, because the parenthetical is the catalog's
        own disambiguation rather than Wikipedia's. Searching finds
        "Binghamton University" and "United States Military Academy", whose
        faculty categories hold 144 and 338 people.
        """
        body = self.query(
            WIKIPEDIA_HOST, action="query", list="search", srsearch=name,
            srnamespace="0", srlimit="1",
        )
        hits = body.get("query", {}).get("search", [])
        return hits[0]["title"] if hits else None

    def search_faculty_category(self, name: str) -> str | None:
        """Find a school's faculty category when its name is irregular.

        Last resort, and it earns its place: Hamilton College's category is
        "Hamilton College (New York) faculty", and Cal State Fullerton's has a
        stray comma before "faculty". Searching the category namespace finds
        what the category is actually called instead of guessing.
        """
        body = self.query(
            WIKIPEDIA_HOST, action="query", list="search",
            srsearch=f'intitle:"{name}" intitle:faculty', srnamespace="14", srlimit="1",
        )
        hits = body.get("query", {}).get("search", [])
        return hits[0]["title"] if hits else None

    # -- Wikidata --------------------------------------------------------

    def entities(self, qids: list[str]) -> dict[str, dict[str, Any]]:
        """Claims, English description and sitelinks for each QID."""
        out: dict[str, dict[str, Any]] = {}
        for chunk in _chunks(qids, BATCH):
            body = self.query(
                WIKIDATA_HOST, action="wbgetentities", ids="|".join(chunk),
                props="claims|descriptions|sitelinks|labels", languages="en",
            )
            out.update(body.get("entities", {}))
        return out

    def labels(self, qids: list[str]) -> dict[str, str]:
        """QID -> English label. Used to turn occupation ids into words."""
        out: dict[str, str] = {}
        for chunk in _chunks(qids, BATCH):
            body = self.query(
                WIKIDATA_HOST, action="wbgetentities", ids="|".join(chunk),
                props="labels", languages="en",
            )
            for qid, entity in body.get("entities", {}).items():
                label = (entity.get("labels", {}).get("en") or {}).get("value")
                if label:
                    out[qid] = label
        return out


def _chunks(items: list[str], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


# -- reading claims ------------------------------------------------------


def claim_ids(entity: dict[str, Any], prop: str) -> list[str]:
    """Every item id asserted for `prop`, ignoring novalue/somevalue snaks."""
    ids: list[str] = []
    for claim in entity.get("claims", {}).get(prop, []):
        value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(value, dict) and value.get("id"):
            ids.append(value["id"])
    return ids


def is_human(entity: dict[str, Any]) -> bool:
    return Q_HUMAN in claim_ids(entity, P_INSTANCE_OF)


def has_died(entity: dict[str, Any]) -> bool:
    """A date of death is the only reliable "no longer teaching" signal here.

    Its absence is not proof of life — plenty of items simply lack the
    statement — which is why the field it feeds is called `status` and its
    values are "historical" and "current", not "dead" and "alive".
    """
    return bool(entity.get("claims", {}).get(P_DATE_OF_DEATH))


def english_description(entity: dict[str, Any]) -> str | None:
    return (entity.get("descriptions", {}).get("en") or {}).get("value")


def sitelink_count(entity: dict[str, Any]) -> int:
    """How many language Wikipedias hold an article on this person.

    The prominence proxy: it is measured rather than judged, it needs no
    extra request, and it degrades sensibly — a locally known professor sits
    at 1, a Nobel laureate in the hundreds.
    """
    return len(entity.get("sitelinks", {}))
