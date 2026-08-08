"""Stage 3 — Crawl Profiles (§6 Stage 3).

For each school's discovered directory URL(s) (`data/directories.jsonl`,
Stage 2 output; schools with `directory_urls: []` are not crawl targets):

1. **Enumerate.** Fetch each directory URL through `services.http_client`
   (the single fetch path — this stage never calls httpx directly, never
   bypasses the cache, never works around a robots-disallowed URL). Walk its
   same-registrable-domain anchors, sorting each into "pagination" (another
   page of the *listing* — A-Z letter links, numbered pages, rel=next) or
   "profile" (an individual person's page), per the M4 instructions. Follow
   pagination up to `config.max_directory_pages`; a malformed/cyclical
   "next" link cannot loop forever. Links off the directory's own
   registrable domain (an aggregator, a social network, a conference site)
   are dropped before classification, not merely deprioritized.
2. **Fetch profiles.** For each enumerated profile URL not already `done` in
   `checkpoints/crawl.json` (§9, keyed by the normalized profile URL), fetch
   it, and append a `models.RawProfile` row to `data/profiles_raw.jsonl`
   with a light `parse_hint` (§4.3) — a hint, not extraction; Stage 4 does
   the real work. `checkpoint.mark_done` fires right after each successful
   write, so a crash costs one page. Stops at `config.max_profiles_per_school`
   *new* fetches for the school this run (already-`done` profiles don't
   consume the cap — they're not being fetched again) and logs the
   truncation clearly rather than silently dropping the rest.
3. **404s and dead links** are recorded (the real `http_status`, per §4.3)
   and checkpointed `done` — a confirmed 404 does not need retrying — rather
   than aborting the run. Only an unresolved transport failure (timeout,
   connection error after `http_client`'s own retries) is checkpointed
   `failed` for the next run to retry (§8).
4. **No profile links at all** from a school's directory page(s), despite a
   successful (200) fetch, is the JS-rendered case §6 names: the school is
   flagged `needs_dynamic_render` in the run's notes/log (visible, not
   silent) and skipped — no profiles are fetched for it. The opt-in
   Playwright fallback (§13) is deliberately not implemented here; passing
   `--dynamic` fails loudly rather than pretending to honor it.
"""
from __future__ import annotations

import logging
import re
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Protocol
from urllib.parse import parse_qsl, urljoin, urlsplit

from selectolax.parser import HTMLParser

from ..config import Config
from ..models import Directory, RawProfile, StageSummary
from ..services.checkpoint import CheckpointStore
from ..services.http_client import FetchResult
from ..services.robots import RobotsDisallowedError
from ..utils import normalize_url, registrable_domain

STAGE_NAME = "crawl"

# §6 Stage 3 / M4: same-domain anchors matching these patterns are candidate
# profile links. Checked against the full href (path + query), lowercased.
_PROFILE_PATTERNS = ("/faculty/", "/people/", "/profile", "?id=", "/directory/")

# Assets that the `?id=` pattern above otherwise sweeps in. A real case from the
# first live run: `tools.bard.edu/files/pr/main_news_image.php?id=21490` is a
# news JPEG, matched `?id=`, and was fetched and stored as if it were a person.
# Extensions are checked against the path only, so `?id=` query strings do not
# defeat them.
_ASSET_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".bmp", ".tif", ".tiff",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".gz", ".tar", ".mp3", ".mp4", ".mov", ".avi", ".css", ".js", ".rss", ".xml",
)
# Path segments that mean "static asset", regardless of extension — the Bard
# case ends in `.php` and only serves an image.
_ASSET_PATH_HINTS = ("/files/", "/uploads/", "/assets/", "/static/", "_image", "/media/")

# Query keys that mean "this link re-renders the *same* listing" (an A-Z
# index like `?letter=B`, or `?page=2`) rather than pointing at a person.
_PAGINATION_QUERY_KEYS = {"page", "p", "pg", "letter", "ltr", "start", "offset"}

# Anchor text alone marks pagination when the href-based checks below don't
# already catch it: "Next", a bare page number, or a single A-Z index letter.
_PAGINATION_TEXT_RE = re.compile(
    r"^(next|previous|prev|first|last|»|«|›|‹|>|<|[a-z]|\d{1,4})$", re.IGNORECASE
)
_PAGINATION_PATH_RE = re.compile(r"/page/\d+/?$", re.IGNORECASE)

_ANCHOR_IGNORED_SCHEMES = ("javascript:", "mailto:", "tel:")


class CrawlError(RuntimeError):
    """Fatal Stage 3 error (e.g. missing `data/directories.jsonl`) — not a
    per-item failure."""


class HttpFetcher(Protocol):
    """The subset of `services.http_client.HttpClient` this stage needs. A
    Protocol so tests can inject a fake client without a real network
    stack."""

    def fetch(self, url: str, *, method: str = "GET") -> FetchResult: ...


def run(
    config: Config,
    checkpoint: CheckpointStore,
    logger: logging.Logger,
    http_client: HttpFetcher,
    *,
    limit: int | None = None,
    school_id: str | None = None,
    dynamic: bool = False,
    dry_run: bool = False,
) -> StageSummary:
    """Resumable per profile URL. `dynamic=True` would enable the
    headless-browser fallback for JS-rendered directories, but that fallback
    isn't implemented (§13 keeps it opt-in and off by default) — passing it
    raises `CrawlError` rather than silently ignoring the flag.

    `dry_run=True` reports how many schools would be crawled without making
    any network calls or writing anything.
    """
    if dynamic:
        raise CrawlError(
            "the Playwright headless-render fallback (--dynamic) is not implemented "
            "(§13 keeps it opt-in and off by default); rerun without --dynamic"
        )

    started_at = datetime.now(UTC)
    directories = _load_directories(config.data_dir)
    with_urls = [d for d in directories if d.directory_urls]

    targets = [d for d in with_urls if school_id is None or d.school_id == school_id]
    pending = targets[:limit] if limit is not None else targets
    skipped_schools = len(targets) - len(pending)

    if dry_run:
        return StageSummary(
            stage=STAGE_NAME,
            processed=0,
            skipped=skipped_schools,
            failed=0,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            notes=[f"[dry-run] would crawl {len(pending)} school(s); no network calls made"],
        )

    output_path = Path(config.data_dir) / "profiles_raw.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    processed = 0
    skipped = skipped_schools
    failed = 0
    notes: list[str] = []

    with output_path.open("a", encoding="utf-8") as out:
        for directory in pending:
            result = _crawl_school(config, http_client, checkpoint, directory, out, logger)
            processed += result.fetched
            skipped += result.already_done + result.robots_skipped + result.cap_skipped
            failed += result.failed
            notes.extend(result.notes)

    return StageSummary(
        stage=STAGE_NAME,
        processed=processed,
        skipped=skipped,
        failed=failed,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        notes=notes,
    )


# -- per-school crawl -------------------------------------------------------


@dataclass
class _SchoolCrawlResult:
    fetched: int = 0
    already_done: int = 0
    robots_skipped: int = 0
    cap_skipped: int = 0
    failed: int = 0
    # True when the directory yielded real profiles but visibly only a slice of
    # them. The rows are still written; downstream must not read them as this
    # school's complete faculty.
    partial: bool = False
    notes: list[str] = field(default_factory=list)


def _crawl_school(
    config: Config,
    http_client: HttpFetcher,
    checkpoint: CheckpointStore,
    directory: Directory,
    out: IO[str],
    logger: logging.Logger,
) -> _SchoolCrawlResult:
    school_id = directory.school_id
    result = _SchoolCrawlResult()

    enum_result = _enumerate_directory(
        config, http_client, directory.directory_urls, school_id, logger
    )

    result.notes.append(
        f"{school_id}: {len(enum_result.profile_entries)} profile url(s) enumerated "
        f"across {enum_result.pages_visited} directory page(s)"
    )

    if enum_result.page_cap_hit:
        msg = (
            f"{school_id}: hit max_directory_pages={config.max_directory_pages}; "
            "pagination stopped early, some directory pages were not visited"
        )
        logger.warning(msg, extra={"stage": STAGE_NAME, "school_id": school_id})
        result.notes.append(msg)

    if enum_result.needs_dynamic_render:
        found = len(enum_result.profile_entries)
        if found == 0:
            msg = (
                f"{school_id}: needs_dynamic_render — {enum_result.pages_visited} directory "
                "page(s) fetched successfully but yielded no profile links "
                "(likely a JS-rendered directory; Playwright fallback not implemented, §13)"
            )
            logger.warning(msg, extra={"stage": STAGE_NAME, "school_id": school_id})
            result.notes.append(msg)
            return result

        # Partial capture: the links found are real, so they are still fetched
        # — throwing away genuine professors helps nobody. What must not happen
        # is this reaching a CSV looking complete, so the school is flagged and
        # the count is stated. Stage 5 can then exclude or caveat it.
        msg = (
            f"{school_id}: PARTIAL — {found} profile link(s) enumerated across "
            f"{enum_result.pages_visited} directory page(s), but they all fall under one "
            "letter of the alphabet. The directory almost certainly loads its remaining "
            "sections by script (§13 Playwright fallback not implemented). Crawling what "
            "was found; treat this school's coverage as incomplete."
        )
        logger.warning(msg, extra={"stage": STAGE_NAME, "school_id": school_id})
        result.notes.append(msg)
        result.partial = True

    cap = config.max_profiles_per_school
    attempted = 0

    for profile_url, directory_url in enum_result.profile_entries:
        if checkpoint.is_done(profile_url):
            result.already_done += 1
            continue

        if attempted >= cap:
            result.cap_skipped += 1
            continue

        try:
            fetch_result = http_client.fetch(profile_url)
        except RobotsDisallowedError:
            result.robots_skipped += 1
            logger.info(
                "robots disallowed profile url",
                extra={"stage": STAGE_NAME, "school_id": school_id, "url": profile_url},
            )
            continue
        except Exception as exc:  # noqa: BLE001 - per-profile failure, not fatal to the run
            attempted += 1
            result.failed += 1
            checkpoint.mark_failed(profile_url, str(exc))
            logger.warning(
                "profile fetch failed: %s",
                exc,
                extra={"stage": STAGE_NAME, "school_id": school_id, "url": profile_url},
            )
            continue

        attempted += 1
        raw = RawProfile(
            school_id=school_id,
            profile_url=profile_url,
            directory_url=directory_url,
            html_cache_path=str(fetch_result.cache_path),
            fetched_at=datetime.now(UTC),
            http_status=fetch_result.status,
            parse_hint=_parse_hint(fetch_result.body) if fetch_result.status == 200 else {},
        )
        out.write(raw.model_dump_json())
        out.write("\n")
        out.flush()
        checkpoint.mark_done(profile_url, meta={"http_status": fetch_result.status})
        result.fetched += 1

        if fetch_result.status != 200:
            logger.info(
                "profile url returned %s (recorded, not retried)",
                fetch_result.status,
                extra={"stage": STAGE_NAME, "school_id": school_id, "url": profile_url},
            )

    if result.cap_skipped:
        msg = (
            f"{school_id}: truncated at max_profiles_per_school={cap}; "
            f"{result.cap_skipped} profile url(s) not fetched this run"
        )
        logger.warning(msg, extra={"stage": STAGE_NAME, "school_id": school_id})
        result.notes.append(msg)

    return result


# -- link enumeration ---------------------------------------------------


@dataclass
class _EnumResult:
    profile_entries: list[tuple[str, str]]  # (normalized profile url, page it was found on)
    pages_visited: int
    page_cap_hit: bool
    needs_dynamic_render: bool


def _enumerate_directory(
    config: Config,
    http_client: HttpFetcher,
    directory_urls: list[str],
    school_id: str,
    logger: logging.Logger,
) -> _EnumResult:
    """Walks `directory_urls` (each a Stage 2-discovered entrypoint) and any
    same-domain pagination reachable from them, up to `max_directory_pages`
    total pages for the school (shared across all entrypoints, since a
    malformed loop from any one of them is equally a problem).
    """
    allowed_domains = {registrable_domain(u) for u in directory_urls}
    root_urls = {normalize_url(u) for u in directory_urls}

    visited: set[str] = set()
    queued: set[str] = set(root_urls)
    queue: deque[str] = deque(directory_urls)

    seen_profiles: set[str] = set()
    profile_entries: list[tuple[str, str]] = []
    pages_visited = 0

    while queue and pages_visited < config.max_directory_pages:
        page_url = queue.popleft()
        norm_page = normalize_url(page_url)
        if norm_page in visited:
            continue
        visited.add(norm_page)

        try:
            fetch_result = http_client.fetch(page_url)
        except RobotsDisallowedError:
            logger.info(
                "robots disallowed directory page",
                extra={"stage": STAGE_NAME, "school_id": school_id, "url": page_url},
            )
            continue
        except Exception as exc:  # noqa: BLE001 - one dead directory page isn't fatal
            logger.info(
                "directory page fetch failed: %s",
                exc,
                extra={"stage": STAGE_NAME, "school_id": school_id, "url": page_url},
            )
            continue

        pages_visited += 1
        if fetch_result.status != 200:
            logger.info(
                "directory page returned %s, skipping",
                fetch_result.status,
                extra={"stage": STAGE_NAME, "school_id": school_id, "url": page_url},
            )
            continue

        base_url = fetch_result.final_url or page_url
        for href, text, rel in _extract_anchors(fetch_result.body, base_url):
            domain = registrable_domain(href)
            if domain not in allowed_domains:
                continue

            norm_href = normalize_url(href)
            if norm_href == norm_page or norm_href in root_urls:
                # Self-link or a link back to a known directory entrypoint —
                # never a person, even if it happens to match a profile
                # pattern like "/faculty/".
                if norm_href not in visited and norm_href not in queued:
                    queue.append(href)
                    queued.add(norm_href)
                continue

            kind = _classify_link(href, page_url, text, rel)
            if kind == "pagination":
                if norm_href not in visited and norm_href not in queued:
                    queue.append(href)
                    queued.add(norm_href)
            elif kind == "profile" and norm_href not in seen_profiles:
                seen_profiles.add(norm_href)
                profile_entries.append((norm_href, base_url))

    page_cap_hit = pages_visited >= config.max_directory_pages and len(queue) > 0
    # Zero links is the obvious JS-rendered case. A *narrow* result is the
    # dangerous one: see _looks_alphabetically_partial.
    needs_dynamic_render = pages_visited > 0 and (
        not profile_entries
        or _looks_alphabetically_partial([url for url, _ in profile_entries])
    )

    return _EnumResult(
        profile_entries=profile_entries,
        pages_visited=pages_visited,
        page_cap_hit=page_cap_hit,
        needs_dynamic_render=needs_dynamic_render,
    )


# Below this many profiles, an initial-concentration reading is noise: a small
# department genuinely can have four people whose names all start with A.
_PARTIAL_MIN_PROFILES = 8
_PARTIAL_CONCENTRATION = 0.9


def _looks_alphabetically_partial(profile_urls: list[str]) -> bool:
    """True when the captured profiles all sit under one letter of the alphabet.

    The failure this catches is silent and expensive. An A-Z directory that
    server-renders only its first section, loading B-Z by script on click, hands
    the crawler a page full of real, valid profile links — so nothing errors,
    nothing 404s, and the run reports success having collected perhaps 4% of the
    faculty. Zero links trips the existing `needs_dynamic_render` check; 17 of
    400 does not, and reads as a complete result all the way into the CSV.

    Real faculty lists spread across the alphabet. A large set sharing a single
    initial means the crawler saw one slice of a paginated directory, not a
    small school. Both name orders are checked, since profile slugs appear as
    `susan-aberth` and as `aberth-susan` depending on the site.
    """
    if len(profile_urls) < _PARTIAL_MIN_PROFILES:
        return False

    slugs = [urlsplit(u).path.rstrip("/").rsplit("/", 1)[-1].lower() for u in profile_urls]
    tokenised = [[t for t in s.split("-") if t and t[0].isalpha()] for s in slugs]
    tokenised = [t for t in tokenised if len(t) >= 2]
    if len(tokenised) < _PARTIAL_MIN_PROFILES:
        return False

    # Surnames are compound often enough that a single token position is not
    # enough: `ziad-abu-rish` ends in "rish" but is filed under A. So for each
    # naming convention — given-name first, or surname first — take the set of
    # initials across the *surname side* of each slug, and ask whether one
    # letter appears in nearly all of them.
    for drop in ("first", "last"):
        per_slug_initials = [
            {t[0] for t in (tokens[1:] if drop == "first" else tokens[:-1])} for tokens in tokenised
        ]
        counts = Counter(letter for initials in per_slug_initials for letter in initials)
        if not counts:
            continue
        if max(counts.values()) / len(per_slug_initials) >= _PARTIAL_CONCENTRATION:
            return True
    return False


def _extract_anchors(html: str, base_url: str) -> list[tuple[str, str, str | None]]:
    """`(absolute_href, link_text, rel)` for every usable `<a href>` in
    `html`, relative links resolved against `base_url`. `mailto:`,
    `javascript:`, `tel:` and bare `#fragment` anchors are dropped outright —
    none of them can ever be a directory page or a profile page."""
    tree = HTMLParser(html)
    anchors: list[tuple[str, str, str | None]] = []
    for node in tree.css("a[href]"):
        href = node.attributes.get("href")
        if not href:
            continue
        href = href.strip()
        if not href or href.startswith("#") or href.lower().startswith(_ANCHOR_IGNORED_SCHEMES):
            continue
        resolved = urljoin(base_url, href)
        if not resolved.lower().startswith(("http://", "https://")):
            continue
        text = " ".join((node.text() or "").split())
        rel = node.attributes.get("rel")
        anchors.append((resolved, text, rel))
    return anchors


def _classify_link(href: str, current_page_url: str, text: str, rel: str | None) -> str:
    """`"pagination"` (another page of *this* listing), `"profile"` (an
    individual's page), or `"ignore"`. Pagination is checked first: profile
    patterns like `/faculty/` are broad enough to also match a directory's
    own paginated index (e.g. `/faculty/?letter=B`), so a link classified as
    pagination is never reclassified as a profile.
    """
    rel_norm = (rel or "").lower()
    if "next" in rel_norm or "prev" in rel_norm:
        return "pagination"

    href_parts = urlsplit(href)
    current_parts = urlsplit(current_page_url)
    href_path = href_parts.path.rstrip("/") or "/"
    current_path = current_parts.path.rstrip("/") or "/"
    if href_path == current_path and href_parts.query != current_parts.query:
        query_keys = {key.lower() for key, _ in parse_qsl(href_parts.query)}
        if query_keys & _PAGINATION_QUERY_KEYS:
            return "pagination"

    if _PAGINATION_PATH_RE.search(href_parts.path):
        return "pagination"

    stripped_text = text.strip()
    if stripped_text and _PAGINATION_TEXT_RE.match(stripped_text):
        return "pagination"

    if _is_asset_link(href):
        return "ignore"

    lowered_href = href.lower()
    if any(pattern in lowered_href for pattern in _PROFILE_PATTERNS):
        return "profile"

    return "ignore"


def _is_asset_link(href: str) -> bool:
    """True for images, documents and other static files.

    `?id=` is a legitimate profile pattern on many directories, but it also
    matches asset handlers. Without this, a news photo is fetched, stored and
    handed to Stage 4 as a professor.
    """
    path = urlsplit(href).path.lower()
    return path.endswith(_ASSET_EXTENSIONS) or any(h in path for h in _ASSET_PATH_HINTS)


# -- parse hint ---------------------------------------------------------


def _parse_hint(html: str) -> dict[str, str | None]:
    """Light name/title guess from `<h1>` (preferred) or `<title>` — a hint
    for a human/Stage 4 to sanity-check against, not extraction. A single
    comma splits "Jane Doe, Professor of Biology" into name/title; anything
    else is returned as the name alone."""
    tree = HTMLParser(html)
    h1_node = tree.css_first("h1")
    h1_text = _clean(h1_node.text()) if h1_node is not None else ""
    title_node = tree.css_first("title")
    title_text = _clean(title_node.text()) if title_node is not None else ""

    source = h1_text or title_text
    if not source:
        return {"name": None, "title": None}

    if "," in source:
        name_part, _, title_part = source.partition(",")
        return {"name": name_part.strip() or None, "title": title_part.strip() or None}

    return {"name": source, "title": None}


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())


# -- loading ---------------------------------------------------------------


def _load_directories(data_dir: str | Path) -> list[Directory]:
    path = Path(data_dir) / "directories.jsonl"
    if not path.exists():
        raise CrawlError(
            f"directories not found at {path}. Run `python -m faculty_pipeline discover` first."
        )
    directories: list[Directory] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            directories.append(Directory.model_validate_json(line))
    return directories
