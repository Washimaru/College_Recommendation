"""OpenAlex API access — who publishes from an institution, and on what.

OpenAlex is CC0 and needs no key, only a `mailto` in the User-Agent to reach
the polite pool. What it offers that Wikipedia cannot: *when* someone was
affiliated with an institution, and *what they research*, as a topic hierarchy
(topic -> subfield -> field) rather than an occupation noun.

Three things measured on real data shape this module; see
docs/superpowers/specs/2026-08-14-active-faculty-design.md.

- `last_known_institutions` collides on names — it put epigenetics researchers
  at Chinese universities on ArtCenter College of Design. Nothing here uses it.
- Ever-affiliated is not currently-affiliated: filtering by `affiliations`
  surfaced Yoshua Bengio for MIT, where he was a postdoc in 1991. So the
  question asked here is always about *recent works written from* the
  institution.
- A bare name search for "Berklee" returns Google (Canada), so institutions are
  resolved by homepage and the result is verified before use.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Protocol
from urllib.parse import urlencode, urlsplit

API_ROOT = "https://api.openalex.org"
# OpenAlex's robots.txt allows everything; requests still go through the shared
# HttpClient, so they inherit its per-host rate limit, cache and backoff.
HOST = "api.openalex.org"


class HttpFetcher(Protocol):
    def fetch(self, url: str, *, method: str = "GET") -> Any: ...


class OpenAlexError(RuntimeError):
    """The API answered with an error or an unparseable body."""


def normalize_homepage(url: str | None) -> str | None:
    """Reduce a homepage to `host/path` for comparison.

    The catalog stores "web.mit.edu/" while OpenAlex stores
    "https://web.mit.edu"; neither is wrong and both must match.
    """
    if not url:
        return None
    candidate = url.strip().lower()
    if "//" not in candidate:
        candidate = "https://" + candidate
    parts = urlsplit(candidate)
    host = parts.netloc.removeprefix("www.")
    path = parts.path.rstrip("/")
    return f"{host}{path}" if host else None


class OpenAlexApi:
    """`mailto` puts requests in OpenAlex's polite pool.

    Not a nicety: without it the daily allowance is 1,000 requests and with it
    100,000. The first full run stopped after 63 schools on a quota 429 whose
    `Retry-After` was 21.9 hours, because the pipeline's stock User-Agent has
    no address OpenAlex recognises. Missing address costs quota, never
    correctness — the API works either way.
    """

    def __init__(
        self,
        http: HttpFetcher,
        logger: logging.Logger | None = None,
        mailto: str | None = None,
    ) -> None:
        self._http = http
        self._logger = logger or logging.getLogger(__name__)
        self._mailto = mailto or None
        if not self._mailto:
            self._logger.warning(
                "openalex: no contact address set, so requests use the anonymous pool "
                "(1,000/day instead of 100,000). Set FACULTY_PIPELINE_OPENALEX_MAILTO "
                "to identify yourself."
            )

    def get(self, path: str, **params: str) -> dict[str, Any]:
        url = f"{API_ROOT}/{path.lstrip('/')}"
        if self._mailto:
            params["mailto"] = self._mailto
        if params:
            url += "?" + urlencode(params)
        result = self._http.fetch(url)
        try:
            body = json.loads(result.body)
        except json.JSONDecodeError as exc:
            raise OpenAlexError(f"non-JSON response from {url}") from exc
        if isinstance(body, dict) and body.get("error"):
            raise OpenAlexError(str(body.get("message", body["error"])))
        return body

    # -- institutions ----------------------------------------------------

    def institution_for(self, name: str, homepage: str | None) -> dict[str, Any] | None:
        """The OpenAlex institution for a school, or None if unconfirmed.

        Homepage first, because it is an identifier rather than a guess. A name
        search is tried second and its result is only accepted when the
        homepages agree — "Berklee College of Music" once resolved to Google
        (Canada), and a wrong institution produces a page of confidently wrong
        professors.
        """
        wanted = normalize_homepage(homepage)
        if wanted:
            body = self.get("institutions", search=name, per_page="10")
            for candidate in body.get("results", []):
                if normalize_homepage(candidate.get("homepage_url")) == wanted:
                    return candidate

        body = self.get("institutions", search=name, per_page="1")
        results = body.get("results", [])
        if not results:
            return None
        candidate = results[0]
        if wanted and normalize_homepage(candidate.get("homepage_url")) != wanted:
            self._logger.info(
                "openalex: rejected %r for %r (homepage %r != %r)",
                candidate.get("display_name"), name,
                candidate.get("homepage_url"), homepage,
            )
            return None
        return candidate

    # -- who is publishing from there now --------------------------------

    def recent_author_counts(
        self, institution_id: str, since_year: int, *, limit: int = 60
    ) -> list[tuple[str, str, int]]:
        """`(author_id, display_name, works)` for papers written from there.

        Grouped server-side, so one request answers "who has been publishing
        from this institution lately" without paging through the works
        themselves.
        """
        body = self.get(
            "works",
            filter=f"authorships.institutions.id:{institution_id},"
                   f"from_publication_date:{since_year}-01-01",
            group_by="authorships.author.id",
            per_page=str(limit),
        )
        counts = []
        for group in body.get("group_by", []):
            author_id = str(group.get("key", "")).rsplit("/", 1)[-1]
            if author_id and author_id.startswith("A"):
                counts.append((author_id, group.get("key_display_name", ""), group.get("count", 0)))
        return counts

    def authors(self, author_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Full author records, 50 per request via an id filter."""
        found: dict[str, dict[str, Any]] = {}
        for i in range(0, len(author_ids), 50):
            chunk = author_ids[i : i + 50]
            body = self.get(
                "authors", filter="openalex_id:" + "|".join(chunk), per_page="50",
            )
            for author in body.get("results", []):
                found[author["id"].rsplit("/", 1)[-1]] = author
        return found


# -- reading an author record --------------------------------------------


def research_topics(author: dict[str, Any], limit: int = 4) -> list[str]:
    """What they actually work on, most prominent first."""
    return [t["display_name"] for t in author.get("topics", [])[:limit] if t.get("display_name")]


def research_fields(author: dict[str, Any]) -> list[str]:
    """The coarse OpenAlex fields behind those topics, deduped in order.

    A small vocabulary — "Mathematics", "Physics and Astronomy", "Arts and
    Humanities" — which is what makes both the plausibility check and the
    major filter possible.
    """
    fields: list[str] = []
    for topic in author.get("topics", []):
        name = (topic.get("field") or {}).get("display_name")
        if name and name not in fields:
            fields.append(name)
    return fields


def last_active_year(author: dict[str, Any]) -> int | None:
    years = [c["year"] for c in author.get("counts_by_year", []) if c.get("works_count")]
    return max(years) if years else None
