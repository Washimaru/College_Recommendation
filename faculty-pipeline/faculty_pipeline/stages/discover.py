"""Stage 2 — Discover Directories (§6 Stage 2).

For each school not already `done` in `checkpoints/discover.json`: try
heuristic URLs, query `services.search`, classify candidates via
`services.llm.classify_directory`, check `services.robots`, and append to
`data/directories.jsonl`.

Order, per §6 Stage 2 / the adaptation banner:

1. **Heuristics.** `{homepage}/faculty`, `/people`, `/directory`,
   `/academics/faculty`, and a couple of reasonable siblings. Each is
   fetched through `services.http_client` (the single fetch path — this
   stage never calls httpx directly) and kept only if it resolves: HTTP 200,
   looks like HTML, and isn't a soft-404 (a "not found" page served with a
   200 status, which is common and must be caught, not just checked for
   200).
2. **Search.** `services.search.SearchProvider.search(...)`; with no
   `SEARCH_API_KEY` configured this returns no candidates (never raises,
   never blocks the stage) — see `services/search.py`. Search results are
   validated with the same resolves-and-not-soft-404 check as heuristics.
3. **LLM classification.** Surviving candidates go to
   `llm.classify_directory`, along with a plain-text excerpt of each
   candidate's already-fetched page (`utils.extract_text_excerpt` over the
   `FetchResult.body` step 1/2 already retrieved — never a second fetch),
   which picks/ranks official on-domain directory URL(s) and rejects
   aggregators and non-directory pages using that page content as evidence
   rather than guessing from the URL shape. Its output is UNTRUSTED
   (`services/llm.py`'s docstring) — this stage is the trust boundary: any
   URL the model returns that wasn't in the candidate list it was given is
   dropped, never accepted on the model's say-so alone.
4. **Robots gate.** Each URL the LLM chose is checked again against
   `services.robots` before being recorded; a disallowed URL is dropped
   from `directory_urls` (a correct "we can't crawl this" outcome, not an
   error) and `robots_allowed` is set to `False` to record that a URL was
   removed this way.

A school with no candidates at all (heuristics + search both empty) skips
the LLM call entirely and is recorded with `directory_urls: []`,
`confidence: 0`, `discovery_method: "none"` — "we looked and found nothing"
is a finished result (marked `done`), not a failure to retry. A search or
LLM *error*, by contrast, marks the school `failed` so the next run retries
it (§9).
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from ..config import Config
from ..models import Directory, School, StageSummary
from ..services import sitemap as sitemap_service
from ..services.checkpoint import CheckpointStore
from ..services.http_client import FetchResult, RobotsCheckerLike
from ..services.llm import DirectoryClassification
from ..services.robots import RobotsDisallowedError
from ..services.search import SearchProvider
from ..utils import extract_text_excerpt

# Sitemap-derived profile clusters are self-evident (a URL sitting under
# /directory/faculty/ alongside 123 siblings doesn't need an LLM's opinion),
# so they get a fixed confidence rather than one derived from
# classify_directory. Used only when no directory-page candidate resolved at
# all — the ordinary case where a directory index also resolved runs the
# normal LLM-derived confidence path and simply carries profile_urls along.
SITEMAP_PROFILE_ONLY_CONFIDENCE = 0.9

STAGE_NAME = "discover"

# §6 Stage 2 step 1: "{homepage}/faculty", "/people", "/directory",
# "/academics/faculty", and reasonable siblings.
HEURISTIC_PATHS = (
    "/faculty",
    "/people",
    "/directory",
    "/academics/faculty",
    "/faculty-staff",
    "/staff-directory",
)

# Common soft-404 phrasing: a page that returns HTTP 200 but is actually a
# "not found" page. Checked against the whole (lowercased) body, not just
# the title, since many sites don't set a distinctive <title> on these.
_SOFT_404_MARKERS = (
    "page not found",
    "404 not found",
    "404 error",
    "we couldn't find",
    "we could not find",
    "cannot be found",
    "could not be found",
    "doesn't exist",
    "does not exist",
    "sorry, this page",
    "sorry, we couldn't",
)


class DiscoverError(RuntimeError):
    """Fatal Stage 2 error (e.g. missing `data/schools.jsonl`) — not a
    per-item failure."""


class HttpFetcher(Protocol):
    """The subset of `services.http_client.HttpClient` this stage needs. A
    Protocol so tests can inject a fake client without a real network
    stack."""

    def fetch(self, url: str, *, method: str = "GET") -> FetchResult: ...


class DirectoryClassifier(Protocol):
    """The subset of `services.llm.LLM` this stage needs."""

    def classify_directory(
        self,
        candidates: list[str],
        school: School,
        excerpts: dict[str, str] | None = None,
    ) -> DirectoryClassification: ...


def run(
    config: Config,
    checkpoint: CheckpointStore,
    logger: logging.Logger,
    http_client: HttpFetcher,
    search_provider: SearchProvider,
    llm: DirectoryClassifier,
    robots: RobotsCheckerLike,
    *,
    limit: int | None = None,
    school_id: str | None = None,
    dry_run: bool = False,
) -> StageSummary:
    """Resumable per school_id: skips schools already `done` in the
    checkpoint, unless `school_id` names one school explicitly (matching the
    §12 "iterate on one school" working style: an explicit `--school` run
    always attempts that school regardless of checkpoint state).

    `dry_run=True` reports how many schools would be processed without
    making any network or LLM calls and without writing anything — the
    CLI's global `--dry-run` flag, honored here because this is the first
    stage that touches the network.
    """
    started_at = datetime.now(UTC)
    schools = _load_schools(config.data_dir)

    targets = [s for s in schools if school_id is None or s.school_id == school_id]
    if school_id is not None:
        eligible = list(targets)
    else:
        eligible = [s for s in targets if not checkpoint.is_done(s.school_id)]
    pending = eligible[:limit] if limit is not None else eligible
    skipped = len(targets) - len(pending)

    if dry_run:
        return StageSummary(
            stage=STAGE_NAME,
            processed=0,
            skipped=skipped,
            failed=0,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            notes=[f"[dry-run] would process {len(pending)} school(s); no network calls made"],
        )

    output_path = Path(config.data_dir) / "directories.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    processed = 0
    failed = 0
    found = 0
    empty = 0

    with output_path.open("a", encoding="utf-8") as out:
        for school in pending:
            try:
                directory = _discover_for_school(
                    config, http_client, search_provider, llm, robots, school, logger
                )
            except Exception as exc:  # noqa: BLE001 - per-school failure, not fatal to the run
                failed += 1
                checkpoint.mark_failed(school.school_id, str(exc))
                logger.warning(
                    "discover failed for %s: %s",
                    school.school_id,
                    exc,
                    extra={"stage": STAGE_NAME, "school_id": school.school_id},
                )
                continue

            out.write(directory.model_dump_json())
            out.write("\n")
            out.flush()
            checkpoint.mark_done(
                school.school_id, meta={"directory_urls": directory.directory_urls}
            )
            processed += 1
            if directory.directory_urls:
                found += 1
            else:
                empty += 1

    notes = [f"{found} school(s) with directories found, {empty} with none"]

    return StageSummary(
        stage=STAGE_NAME,
        processed=processed,
        skipped=skipped,
        failed=failed,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        notes=notes,
    )


# -- per-school discovery -------------------------------------------------


def _discover_for_school(
    config: Config,
    http_client: HttpFetcher,
    search_provider: SearchProvider,
    llm: DirectoryClassifier,
    robots: RobotsCheckerLike,
    school: School,
    logger: logging.Logger,
) -> Directory:
    sitemap_result = sitemap_service.discover_sitemap_urls(
        config, http_client, robots, school.homepage, logger, school_id=school.school_id
    )
    sitemap_directory_pages = sitemap_service.find_directory_pages(sitemap_result.urls)
    sitemap_clusters = sitemap_service.find_profile_clusters(
        sitemap_result.urls, exclude=set(sitemap_directory_pages)
    )
    profile_urls = sitemap_service.largest_profile_cluster(sitemap_clusters)

    candidates, excerpts, used_sitemap, used_heuristic, used_search = _discover_candidates(
        http_client,
        search_provider,
        school,
        logger,
        config.directory_excerpt_max_chars,
        sitemap_directory_pages,
    )

    if not candidates:
        if profile_urls:
            # Self-evident: a cluster of sibling profile URLs from the
            # sitemap needs no LLM judgment even though no directory-index
            # candidate resolved (or resolved but was rejected/dead).
            return Directory(
                school_id=school.school_id,
                directory_urls=[],
                profile_urls=profile_urls,
                discovery_method="sitemap",
                robots_allowed=True,
                confidence=SITEMAP_PROFILE_ONLY_CONFIDENCE,
                notes=(
                    f"{len(profile_urls)} profile url(s) found directly in the sitemap; "
                    "no directory index page candidate resolved"
                ),
            )
        return Directory(
            school_id=school.school_id,
            directory_urls=[],
            discovery_method=_method_label(used_sitemap, used_heuristic, used_search),
            robots_allowed=True,
            confidence=0.0,
            notes="no candidate directory URLs resolved via heuristics or search",
        )

    classification = llm.classify_directory(candidates, school, excerpts=excerpts)

    # Trust boundary: never accept a URL the LLM invented outside the
    # candidate set it was given (see services/llm.py's module docstring).
    candidate_set = set(candidates)
    raw_urls = classification.get("directory_urls", [])
    trusted_urls = [u for u in raw_urls if isinstance(u, str) and u in candidate_set]
    dropped_invented = len(raw_urls) - len(trusted_urls)

    try:
        confidence = float(classification.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    allowed_urls, robots_allowed = _apply_robots_gate(
        robots, trusted_urls, config.user_agent, logger, school.school_id
    )

    # Empty (or emptied-by-robots) result is a finished "found nothing", not
    # a partial success — its confidence is always 0 (§4.2 / prompt).
    if not allowed_urls:
        confidence = 0.0

    notes_parts: list[str] = []
    raw_notes = classification.get("notes")
    if isinstance(raw_notes, str) and raw_notes.strip():
        notes_parts.append(raw_notes.strip())
    if dropped_invented:
        notes_parts.append(
            f"dropped {dropped_invented} LLM-suggested URL(s) not in the candidate set"
        )
    if not robots_allowed:
        notes_parts.append("one or more chosen URLs were dropped by robots.txt")

    return Directory(
        school_id=school.school_id,
        directory_urls=allowed_urls,
        profile_urls=profile_urls,
        discovery_method=_method_label(used_sitemap, used_heuristic, used_search),
        robots_allowed=robots_allowed,
        confidence=confidence,
        notes="; ".join(notes_parts) if notes_parts else None,
    )


def _discover_candidates(
    http_client: HttpFetcher,
    search_provider: SearchProvider,
    school: School,
    logger: logging.Logger,
    excerpt_max_chars: int,
    sitemap_directory_pages: list[str],
) -> tuple[list[str], dict[str, str], bool, bool, bool]:
    """Returns `(candidate_urls, excerpts, used_sitemap, used_heuristic, used_search)`.

    `excerpts` maps each surviving candidate URL to a plain-text excerpt of
    the same page body the resolve-check (`_try_fetch`) already fetched and
    cached — no second fetch. A candidate whose resolve-check body was empty
    simply has no entry; `llm.classify_directory` falls back to judging that
    URL alone rather than crashing.

    Sitemap-derived directory-index pages are tried first (a candidate
    source ahead of the heuristics, per the sitemap-recall fix), then
    heuristics, then search — all through the same `_try_fetch` resolve
    check and the same `llm.classify_directory` call below, so the sitemap
    doesn't weaken the existing content-based classification, only feeds it
    a better candidate.
    """
    seen: set[str] = set()
    candidates: list[str] = []
    excerpts: dict[str, str] = {}

    used_sitemap = False
    for url in sitemap_directory_pages:
        if url in seen:
            continue
        result = _try_fetch(http_client, url, logger, school.school_id)
        if result is not None:
            seen.add(url)
            candidates.append(url)
            excerpt = extract_text_excerpt(result.body, excerpt_max_chars)
            if excerpt:
                excerpts[url] = excerpt
            used_sitemap = True

    used_heuristic = False
    for url in _heuristic_urls(school.homepage):
        if url in seen:
            continue
        result = _try_fetch(http_client, url, logger, school.school_id)
        if result is not None:
            seen.add(url)
            candidates.append(url)
            excerpt = extract_text_excerpt(result.body, excerpt_max_chars)
            if excerpt:
                excerpts[url] = excerpt
            used_heuristic = True

    used_search = False
    query = f"{school.name} official faculty directory"
    for search_result in search_provider.search(query):
        url = search_result.url
        if url in seen:
            continue
        result = _try_fetch(http_client, url, logger, school.school_id)
        if result is not None:
            seen.add(url)
            candidates.append(url)
            excerpt = extract_text_excerpt(result.body, excerpt_max_chars)
            if excerpt:
                excerpts[url] = excerpt
            used_search = True

    return candidates, excerpts, used_sitemap, used_heuristic, used_search


def _heuristic_urls(homepage: str) -> list[str]:
    base = homepage.rstrip("/")
    return [base + path for path in HEURISTIC_PATHS]


def _try_fetch(
    http_client: HttpFetcher, url: str, logger: logging.Logger, school_id: str
) -> FetchResult | None:
    """Fetches `url` through `http_client` (the single fetch path — this is
    also where the page content later used as classify_directory evidence
    comes from) and returns the `FetchResult` iff the candidate "resolves":
    200, looks like HTML, and isn't a soft-404. Returns `None` rather than
    raising for a dead/disallowed candidate — one candidate failing isn't
    fatal to the school. Every fetch goes through `http_client`, so a URL
    disallowed by robots.txt raises `RobotsDisallowedError` here rather than
    ever reaching the network — that's a correct "no directory from this
    URL" outcome, logged and excluded, not an error to work around."""
    try:
        result = http_client.fetch(url)
    except RobotsDisallowedError:
        logger.info(
            "robots disallowed candidate url",
            extra={"stage": STAGE_NAME, "school_id": school_id, "url": url},
        )
        return None
    except Exception as exc:  # noqa: BLE001 - one candidate failing isn't fatal to the school
        logger.debug(
            "candidate fetch failed: %s",
            exc,
            extra={"stage": STAGE_NAME, "school_id": school_id, "url": url},
        )
        return None

    if result.status != 200:
        return None
    if not _looks_like_html(result.body):
        return None
    if _looks_soft_404(result.body):
        return None
    return result


def _looks_like_html(body: str) -> bool:
    head = body[:2000].lower()
    return "<html" in head or "<body" in head or "<!doctype html" in head


def _looks_soft_404(body: str) -> bool:
    lowered = body.lower()
    return any(marker in lowered for marker in _SOFT_404_MARKERS)


def _apply_robots_gate(
    robots: RobotsCheckerLike,
    directory_urls: list[str],
    user_agent: str,
    logger: logging.Logger,
    school_id: str,
) -> tuple[list[str], bool]:
    allowed: list[str] = []
    any_disallowed = False
    for url in directory_urls:
        if robots.is_allowed(url, user_agent):
            allowed.append(url)
        else:
            any_disallowed = True
            logger.info(
                "robots disallowed chosen directory url",
                extra={"stage": STAGE_NAME, "school_id": school_id, "url": url},
            )
    return allowed, not any_disallowed


def _method_label(used_sitemap: bool, used_heuristic: bool, used_search: bool) -> str:
    sources = (
        (used_sitemap, "sitemap"),
        (used_heuristic, "heuristic"),
        (used_search, "search"),
    )
    parts = [label for used, label in sources if used]
    return "+".join(parts) if parts else "none"


def _load_schools(data_dir: str | Path) -> list[School]:
    path = Path(data_dir) / "schools.jsonl"
    if not path.exists():
        raise DiscoverError(
            f"schools not found at {path}. Run `python -m faculty_pipeline load` first."
        )
    schools: list[School] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            schools.append(School.model_validate_json(line))
    return schools
