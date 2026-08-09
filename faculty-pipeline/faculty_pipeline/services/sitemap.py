"""Published-sitemap candidate source for Stage 2 discovery (§6 Stage 2
addendum).

The URL heuristics (`/faculty`, `/people`, `/directory`, ...) mostly hit HR
portals, marketing pages and *department listings* — the content-based LLM
classifier in `discover.py` correctly rejects them, and Stage 3 is left with
nothing to crawl. A school's own published XML sitemap sidesteps this
entirely: it is a file the site publishes specifically so crawlers do not
have to spider it, and it very often lists individual faculty profile pages
directly (e.g. Agnes Scott's sitemap has 124 `/directory/faculty/<name>.html`
entries alongside the directory index itself).

This module has two jobs:

1. `discover_sitemap_urls` — find and fetch a school's sitemap(s) (following
   `Sitemap:` directives from `services/robots.py`, or the `/sitemap.xml`
   convention as a fallback) and flatten sitemap-index recursion into one
   list of URLs. **Every fetch goes through `services.http_client`** — the
   single fetch path (robots-gated, rate-limited, cached) — same posture as
   `discover.py` and `crawl.py`. Never raises: a malformed sitemap, a 404, or
   no sitemap at all all just mean "no URLs from this source", the same as a
   heuristic path that 404s.
2. `find_directory_pages` / `find_profile_clusters` — classify that flat URL
   list into directory-index candidates (fed into the *existing* LLM
   candidate pipeline in `discover.py`, unchanged) and profile-URL clusters
   (a path segment repeated across many sibling URLs under one parent — the
   far more valuable signal, self-evident enough that it skips LLM
   classification entirely; see `discover.py`).
"""
from __future__ import annotations

import gzip
import logging
from collections import deque
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from ..config import Config
from .http_client import FetchResult
from .robots import RobotsDisallowedError

# Path segments that mean "this is a faculty/people directory," substring
# matched the same way stages/crawl.py's _PROFILE_PATTERNS is — a hyphenated
# variant like "faculty-staff" still matches "faculty" and "staff".
_DIRECTORY_HINTS = ("faculty", "people", "directory", "staff")

_INDEX_BASENAMES = ("", "index.html", "index.htm", "index.php", "index.asp", "index.aspx")

# Below this many siblings under one parent path, "many URLs under a common
# parent" is noise rather than signal — a small department page linking a
# handful of related pages is not a faculty-profile cluster.
_MIN_PROFILE_CLUSTER_SIZE = 5


class HttpFetcher(Protocol):
    """The subset of `services.http_client.HttpClient` this module needs. A
    Protocol so tests can inject a fake client without a real network stack
    (same pattern as stages/discover.py and stages/crawl.py)."""

    def fetch(self, url: str, *, method: str = "GET") -> FetchResult: ...


class RobotsSitemapSource(Protocol):
    """The subset of `services.robots.RobotsChecker` this module needs."""

    def sitemaps(self, url: str) -> list[str]: ...


@dataclass(frozen=True)
class SitemapResult:
    """Flattened output of `discover_sitemap_urls`: every `<loc>` URL found
    across all `urlset` documents reached (sitemap-index documents are
    recursed into, not included themselves)."""

    urls: list[str]
    documents_fetched: int
    truncated: bool  # hit max_sitemap_documents and/or max_sitemap_urls


def discover_sitemap_urls(
    config: Config,
    http_client: HttpFetcher,
    robots: RobotsSitemapSource,
    homepage: str,
    logger: logging.Logger,
    *,
    school_id: str = "",
) -> SitemapResult:
    """Finds a school's sitemap(s) and returns every URL they list.

    Seed documents: `robots.sitemaps(homepage)` (no extra fetch — reuses
    robots.py's already-cached robots.txt parse), falling back to
    `{homepage}/sitemap.xml` when robots advertises none. Sitemap-index
    documents are recursed into (Auburn's `sitemap.xml` is an index whose
    only entry is `sitemap-main.xml`), up to `config.max_sitemap_documents`
    total document fetch attempts and `config.max_sitemap_urls` total URLs
    collected — some university sitemaps are enormous. `.gz` entries are
    transparently decompressed.

    Never raises. A transport error, a disallowed-by-robots URL, a non-200
    status, or malformed XML on any one document is logged and treated as
    "this document contributed nothing" — the run continues with whatever
    else is queued, and a school with no sitemap at all simply gets back an
    empty `SitemapResult`.
    """
    seeds = _seed_sitemap_urls(robots, homepage, logger, school_id)

    queue: deque[str] = deque(seeds)
    seen_docs: set[str] = set(seeds)
    urls: list[str] = []
    attempted = 0
    truncated = False

    while queue:
        if attempted >= config.max_sitemap_documents:
            truncated = True
            break
        doc_url = queue.popleft()
        attempted += 1

        body = _fetch_sitemap_body(http_client, doc_url, logger, school_id)
        if body is None:
            continue

        kind, locs = _parse_sitemap_xml(body, logger, doc_url, school_id)
        if kind == "sitemapindex":
            for loc in locs:
                if loc not in seen_docs:
                    seen_docs.add(loc)
                    queue.append(loc)
            continue

        for loc in locs:
            if len(urls) >= config.max_sitemap_urls:
                truncated = True
                break
            urls.append(loc)
        if len(urls) >= config.max_sitemap_urls:
            truncated = True
            break

    return SitemapResult(urls=urls, documents_fetched=attempted, truncated=truncated)


def _seed_sitemap_urls(
    robots: RobotsSitemapSource, homepage: str, logger: logging.Logger, school_id: str
) -> list[str]:
    try:
        advertised = robots.sitemaps(homepage)
    except Exception as exc:  # noqa: BLE001 - a broken robots source must not block discovery
        logger.debug(
            "robots sitemap lookup failed: %s",
            exc,
            extra={"stage": "discover", "school_id": school_id, "url": homepage},
        )
        advertised = []
    if advertised:
        return list(advertised)
    return [homepage.rstrip("/") + "/sitemap.xml"]


def _fetch_sitemap_body(
    http_client: HttpFetcher, doc_url: str, logger: logging.Logger, school_id: str
) -> str | None:
    try:
        result = http_client.fetch(doc_url)
    except RobotsDisallowedError:
        logger.info(
            "robots disallowed sitemap document",
            extra={"stage": "discover", "school_id": school_id, "url": doc_url},
        )
        return None
    except Exception as exc:  # noqa: BLE001 - one bad sitemap document isn't fatal
        logger.debug(
            "sitemap document fetch failed: %s",
            exc,
            extra={"stage": "discover", "school_id": school_id, "url": doc_url},
        )
        return None

    if result.status != 200:
        return None

    body = result.body
    if urlsplit(doc_url).path.lower().endswith(".gz"):
        try:
            body = gzip.decompress(body.encode("latin-1")).decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001 - malformed gzip -> no URLs, not a crash
            logger.debug(
                "failed to decompress .gz sitemap: %s",
                exc,
                extra={"stage": "discover", "school_id": school_id, "url": doc_url},
            )
            return None
    return body


def _parse_sitemap_xml(
    xml_text: str, logger: logging.Logger, doc_url: str, school_id: str
) -> tuple[str, list[str]]:
    """`("sitemapindex" | "urlset", [<loc> text...])`. Malformed XML returns
    `("urlset", [])` — empty, never raises."""
    try:
        root = ET.fromstring(xml_text)  # noqa: S314 - trusted-enough sitemap XML, no DTD/entities
    except ET.ParseError as exc:
        logger.info(
            "malformed sitemap XML: %s",
            exc,
            extra={"stage": "discover", "school_id": school_id, "url": doc_url},
        )
        return "urlset", []

    locs = [
        loc.strip()
        for node in root.iter()
        if _local_name(node.tag) == "loc" and node.text and node.text.strip()
        for loc in [node.text.strip()]
    ]
    root_kind = "sitemapindex" if _local_name(root.tag) == "sitemapindex" else "urlset"
    return root_kind, locs


def _local_name(tag: str) -> str:
    """Strips an ElementTree `{namespace}tag` prefix. Sitemap XML always
    declares the `http://www.sitemaps.org/schemas/sitemap/0.9` namespace, but
    matching by local name (rather than hardcoding that URI) tolerates the
    handful of real sitemaps that omit or vary it."""
    return tag.rsplit("}", 1)[-1]


# --------------------------------------------------------------------------
# Classifying the flat URL list: directory-index candidates vs. profile
# clusters (§ discover.py integration).
# --------------------------------------------------------------------------


def find_directory_pages(urls: list[str]) -> list[str]:
    """Sitemap URLs that look like a faculty/people/staff directory *index*
    page — `/faculty/`, `/people/`, `/directory/faculty/index.html` — as
    opposed to an individual profile under one. These are handed to
    `discover.py` as ordinary candidates: fetched, excerpted, and classified
    by the existing content-based LLM step, unchanged.
    """
    pages: list[str] = []
    for url in urls:
        path = urlsplit(url).path
        lowered = path.lower()
        if not any(hint in lowered for hint in _DIRECTORY_HINTS):
            continue
        stripped = lowered.rstrip("/")
        basename = stripped.rsplit("/", 1)[-1] if stripped else ""
        if basename in _INDEX_BASENAMES:
            pages.append(url)
            continue
        stem = basename.rsplit(".", 1)[0]
        if stem in _DIRECTORY_HINTS:
            pages.append(url)
    return pages


def find_profile_clusters(
    urls: list[str], exclude: set[str] | None = None
) -> dict[str, list[str]]:
    """Groups sitemap URLs by parent path, keeping only groups with at least
    `_MIN_PROFILE_CLUSTER_SIZE` members whose path mentions a directory hint
    — the "124 URLs under `/directory/faculty/`" signal. `exclude` should be
    the directory-index pages from `find_directory_pages`, so an index is
    never counted as one of its own cluster's profiles.
    """
    exclude = exclude or set()
    groups: dict[str, list[str]] = {}
    for url in urls:
        if url in exclude:
            continue
        parsed = urlsplit(url)
        path = parsed.path
        if not path or path.endswith("/"):
            continue  # no filename component -> can't be an individual profile page
        if not any(hint in path.lower() for hint in _DIRECTORY_HINTS):
            continue
        parent = path.rsplit("/", 1)[0]
        key = f"{parsed.scheme}://{parsed.netloc}{parent}/"
        groups.setdefault(key, []).append(url)
    return {
        parent: members
        for parent, members in groups.items()
        if len(members) >= _MIN_PROFILE_CLUSTER_SIZE
    }


def largest_profile_cluster(clusters: dict[str, list[str]]) -> list[str] | None:
    """The single biggest profile cluster, or `None` if there isn't one.
    Deterministic tie-break on the parent-path key."""
    if not clusters:
        return None
    best_parent = max(clusters, key=lambda k: (len(clusters[k]), k))
    return list(clusters[best_parent])
