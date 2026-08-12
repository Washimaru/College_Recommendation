"""Stage 5 — Export CSV (§6 Stage 5).

1. Read `data/profiles_clean.jsonl`, group by `school_id`.
2. Filter to rows meeting `config.min_confidence` (§13, default 0.5) — a row
   below the floor stays in the JSONL for audit but is left out of every
   CSV.
3. Write `output/by_school/<slug>.csv` per school with at least one kept
   row (§4.4 column order, UTF-8).
4. Concatenate into `output/master.csv`, identical columns — the union of
   every per-school CSV, not a resample of the JSONL, so "what's in
   master.csv" and "what's in by_school/*.csv" can never disagree.
5. Print a `StageSummary` — including, plainly, how many schools are
   incomplete — and write `output/coverage.csv` (one row per school with
   any clean data, whether or not it cleared the confidence floor):
   `school_id`, `school_name`, `professors_in_csv`,
   `professors_below_confidence`, `partial_coverage`, `capped_at_limit`,
   `incomplete`. This is a *sibling* report, not a new §4.4 column — the
   per-row schema is unchanged.

Not checkpointed per-item (no network calls) — reruns simply overwrite the
CSVs deterministically, same as Stage 1.

**Two independent, invisible ways a school's CSV can be incomplete** — the
CLAUDE.md instruction this stage exists to satisfy:

1. **Alphabetically-partial capture.** `crawl.py`'s
   `_looks_alphabetically_partial` catches a directory that only
   server-rendered one A-Z slice *at crawl time*, over whatever profile
   links enumeration found that run. That flag is never persisted anywhere
   crawl.py writes to disk — it only reaches a log line and that run's
   `StageSummary` notes, both ephemeral. So export.py does not try to go
   excavate it from `logs/`; instead it re-runs the *same* check (via
   `utils.looks_alphabetically_partial`, the shared implementation) over
   the `profile_url`s of the rows that actually made it into each school's
   CSV. This is strictly more useful for a CSV consumer: it reflects the
   school's *final* coverage after confidence filtering, not just what one
   crawl run saw, and it still catches the case whether or not crawl.py
   happened to flag it (e.g. a `--limit`/`--school` partial crawl, or a
   school whose partial slice happened to clear `max_directory_pages`
   cleanly). A flagged school's CSV is still written in full — throwing
   away real professors helps no one — but `output/coverage.csv` and the
   run's notes/log make the gap visible rather than letting a 17-of-400 CSV
   read as complete.

2. **`max_profiles_per_school` truncation.** `crawl.py` also stops a
   school's fetches once it hits `config.max_profiles_per_school` new
   profiles in a run (`result.cap_skipped`), and — like the partial flag
   above — that fact only reaches a log line, never a durable artifact.
   Rather than parse `logs/*.log` (a format not meant for machine
   consumption, and rotated/rewritten across runs), export.py infers it
   from `data/profiles_raw.jsonl`, which *is* durable: a school with at
   least `config.max_profiles_per_school` distinct fetched profile URLs on
   record almost certainly hit the cap at some point (a school that
   happens to have *exactly* that many faculty and was never truncated is
   the one false positive this can't rule out — rare enough, and safe
   enough to over-flag rather than under-flag, that it's noted here rather
   than engineered around). `data/profiles_raw.jsonl` is optional input for
   this stage (unlike `profiles_clean.jsonl`): its absence just means this
   column reads `"unknown"` rather than asserting a coverage claim export.py
   cannot back up.
"""
from __future__ import annotations

import csv
import json
import logging
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from ..config import Config
from ..models import Professor, StageSummary
from ..services.checkpoint import CheckpointStore
from ..utils import classify_role, looks_alphabetically_partial, slugify

STAGE_NAME = "export"

# §4.4, in order. This is also the CSV header row for both per-school and
# master CSVs.
CSV_COLUMNS = [
    "school_id",
    "school_name",
    "professor_name",
    "title",
    "is_faculty",
    "department",
    "email",
    "phone",
    "research_interests",
    "profile_url",
    "directory_url",
    "extraction_confidence",
    "extracted_at",
]

_COVERAGE_COLUMNS = [
    "school_id",
    "school_name",
    "professors_in_csv",
    "professors_below_confidence",
    "professors_excluded_as_non_faculty",
    "source_urls_fetched",
    "source_urls_dead",
    "partial_coverage",
    "capped_at_limit",
    "incomplete",
]


def resolved_role(professor: Professor) -> bool | None:
    """The faculty judgment for a row, deriving it from the title when the
    row does not carry one.

    Rows extracted before `is_faculty` existed have it as `None`, and
    re-running extract on them would cost an LLM call each for a question the
    title already answers. Deriving here means the fix applies to data
    already on disk.
    """
    if professor.is_faculty is not None:
        return professor.is_faculty
    return classify_role(professor.title)


class ExportError(RuntimeError):
    """Fatal Stage 5 error (e.g. missing `data/profiles_clean.jsonl`) — not
    a per-item failure."""


def run(
    config: Config,
    checkpoint: CheckpointStore,  # unused; see module docstring (not checkpointed per-item)
    logger: logging.Logger,
    *,
    dry_run: bool = False,
) -> StageSummary:
    """Read `data/profiles_clean.jsonl`, filter by `config.min_confidence`,
    and write the per-school and master CSVs plus `output/coverage.csv`.

    `dry_run=True` runs the full plan (read, group, filter, partial-coverage
    check) and returns the summary that *would* be written, without
    touching disk — matching Stage 1's `dry_run` behavior, since this stage
    likewise has no network call to short-circuit before.
    """
    started_at = datetime.now(UTC)
    professors, malformed = _load_clean_profiles(config.data_dir, logger)

    by_school: dict[str, list[Professor]] = defaultdict(list)
    for professor in professors:
        by_school[professor.school_id].append(professor)

    kept_by_school: dict[str, list[Professor]] = {}
    below_confidence = 0
    # A named administrator on a `/people/` page is a real person correctly
    # extracted from a real page — just not a professor. Excluded from the
    # CSVs, kept in the JSONL, and counted here so the loss is visible.
    non_faculty_by_school: dict[str, int] = {}
    for school_id, rows in by_school.items():
        faculty = [r for r in rows if resolved_role(r) is not False]
        non_faculty_by_school[school_id] = len(rows) - len(faculty)
        kept = [r for r in faculty if r.extraction_confidence >= config.min_confidence]
        below_confidence += len(faculty) - len(kept)
        if kept:
            kept_by_school[school_id] = kept

    non_faculty = sum(non_faculty_by_school.values())

    partial_school_ids = {
        school_id
        for school_id, rows in kept_by_school.items()
        if looks_alphabetically_partial([r.profile_url for r in rows])
    }

    raw_counts = _load_raw_profile_counts(config.data_dir)
    dead_counts = _load_dead_source_counts(config.data_dir)
    capped_school_ids = {
        school_id
        for school_id in by_school
        if raw_counts is not None and raw_counts.get(school_id, 0) >= config.max_profiles_per_school
    }

    notes: list[str] = []
    for school_id in sorted(partial_school_ids):
        count = len(kept_by_school[school_id])
        msg = (
            f"{school_id}: PARTIAL COVERAGE — the {count} professor row(s) in this school's "
            "CSV all fall under one letter of the alphabet; this almost always means the "
            "directory was captured incompletely upstream (see crawl.py's alphabetical-"
            "partial check). Do not treat this school's CSV as its complete faculty; see "
            "output/coverage.csv."
        )
        logger.warning(msg, extra={"stage": STAGE_NAME, "school_id": school_id})
        notes.append(msg)
    for school_id in sorted(capped_school_ids - partial_school_ids):
        msg = (
            f"{school_id}: CAPPED — at least {config.max_profiles_per_school} profile url(s) "
            "were fetched for this school (config.max_profiles_per_school), which almost "
            "always means crawl.py truncated its directory rather than exhausting it. Do not "
            "treat this school's CSV as its complete faculty; see output/coverage.csv."
        )
        logger.warning(msg, extra={"stage": STAGE_NAME, "school_id": school_id})
        notes.append(msg)

    for school_id in sorted(by_school):
        entry = (dead_counts or {}).get(school_id)
        if not entry:
            continue
        fetched, dead = entry
        if fetched and dead / fetched >= _STALE_SOURCE_SHARE:
            msg = (
                f"{school_id}: STALE SOURCE — {dead} of {fetched} listed profile url(s) "
                f"({dead / fetched:.0%}) no longer resolve. The rows that made the CSV are "
                "real; the directory this school publishes is out of date, so treat its "
                "count as a floor."
            )
            logger.warning(msg, extra={"stage": STAGE_NAME, "school_id": school_id})
            notes.append(msg)

    total_rows = sum(len(rows) for rows in kept_by_school.values())
    total_schools = len(by_school)

    incomplete_note = _incomplete_summary_note(
        total_schools, partial_school_ids, capped_school_ids, raw_counts is None
    )

    if dry_run:
        notes.insert(0, incomplete_note)
        notes.insert(
            0,
            f"[dry-run] would write {len(kept_by_school)} school CSV(s), {total_rows} row(s) "
            f"total; {below_confidence} row(s) below min_confidence={config.min_confidence}; "
            f"{non_faculty} row(s) excluded as non-faculty; no files written",
        )
        return StageSummary(
            stage=STAGE_NAME,
            processed=0,
            skipped=total_rows + below_confidence,
            failed=malformed,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            notes=notes,
        )

    by_school_dir = Path(config.output_dir) / "by_school"
    by_school_dir.mkdir(parents=True, exist_ok=True)

    all_rows: list[Professor] = []
    used_slugs: set[str] = set()
    for school_id in sorted(kept_by_school):
        rows = sorted(kept_by_school[school_id], key=lambda r: r.professor_name)
        slug = _unique_slug(school_id, used_slugs)
        _write_csv(by_school_dir / f"{slug}.csv", rows)
        all_rows.extend(rows)

    all_rows.sort(key=lambda r: (r.school_id, r.professor_name))
    _write_csv(Path(config.output_dir) / "master.csv", all_rows)
    _write_coverage_report(
        Path(config.output_dir) / "coverage.csv",
        by_school,
        kept_by_school,
        partial_school_ids,
        capped_school_ids,
        raw_counts,
        non_faculty_by_school,
        dead_counts,
    )

    notes.insert(0, incomplete_note)
    notes.insert(
        0,
        f"{len(kept_by_school)} school(s), {total_rows} professor(s) written to "
        f"output/master.csv; {below_confidence} row(s) skipped below "
        f"min_confidence={config.min_confidence}; "
        f"{non_faculty} row(s) excluded as non-faculty (administrators and staff)",
    )

    return StageSummary(
        stage=STAGE_NAME,
        processed=total_rows,
        skipped=below_confidence,
        failed=malformed,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        notes=notes,
    )


def _incomplete_summary_note(
    total_schools: int,
    partial_school_ids: set[str],
    capped_school_ids: set[str],
    raw_counts_unavailable: bool,
) -> str:
    """The CLAUDE.md instruction, verbatim: "the summary must state plainly
    how many schools are incomplete." Always emitted — including when the
    count is zero — so a clean run says so as plainly as an incomplete one
    does, rather than incompleteness only being visible by its absence."""
    incomplete = partial_school_ids | capped_school_ids
    note = (
        f"{len(incomplete)} of {total_schools} school(s) with clean data are incomplete "
        f"({len(partial_school_ids)} alphabetically-partial, {len(capped_school_ids)} capped "
        f"at max_profiles_per_school) — see output/coverage.csv"
    )
    if raw_counts_unavailable:
        note += (
            "; data/profiles_raw.jsonl not found, so capped_at_limit could not be determined "
            "and is 'unknown' for every school in coverage.csv"
        )
    return note


# -- loading --------------------------------------------------------------


def _load_clean_profiles(
    data_dir: str | Path, logger: logging.Logger
) -> tuple[list[Professor], int]:
    path = Path(data_dir) / "profiles_clean.jsonl"
    if not path.exists():
        raise ExportError(
            f"clean profiles not found at {path}. Run `python -m faculty_pipeline extract` first."
        )
    professors: list[Professor] = []
    malformed = 0
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            professors.append(Professor.model_validate_json(line))
        except Exception as exc:  # noqa: BLE001 - one bad line shouldn't abort the export
            malformed += 1
            logger.warning(
                "export: skipping malformed row at %s:%d: %s",
                path,
                lineno,
                exc,
                extra={"stage": STAGE_NAME},
            )
    return professors, malformed


def _load_dead_source_counts(data_dir: str | Path) -> dict[str, tuple[int, int]] | None:
    """`(fetched, dead)` per school from `data/profiles_raw.jsonl`.

    A directory that still lists people the site has deleted is ordinary — 15%
    of Agnes Scott's sitemap-listed profiles 404, and 17% of ArtCenter's. The
    crawler already refuses to turn a 404 into a row; this is what says so, so
    a school whose source listing is a third dead is visibly different from a
    current one. `None` when the file is absent, for the same reason as
    `_load_raw_profile_counts`: no evidence is not evidence of zero.
    """
    path = Path(data_dir) / "profiles_raw.jsonl"
    if not path.exists():
        return None
    seen: dict[str, dict[str, int]] = defaultdict(dict)
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            school_id = record["school_id"]
            profile_url = record["profile_url"]
            status = int(record["http_status"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
        # Last status wins: a URL refetched after a transient failure is
        # judged on what it returned most recently.
        seen[school_id][profile_url] = status
    return {
        school_id: (len(statuses), sum(1 for s in statuses.values() if s != 200))
        for school_id, statuses in seen.items()
    }


def _load_raw_profile_counts(data_dir: str | Path) -> dict[str, int] | None:
    """Distinct `profile_url` count per `school_id` from
    `data/profiles_raw.jsonl`, the durable signal Stage 5 uses to infer
    `max_profiles_per_school` truncation (see module docstring, point 2).
    Returns `None` — not `{}` — when the file doesn't exist at all, so the
    caller can tell "no raw data to check" apart from "checked, found
    nothing," and report `capped_at_limit` as `unknown` rather than `false`.
    Malformed lines are skipped rather than raising: this is a best-effort
    coverage signal, not the row data itself, and profiles_clean.jsonl
    already went through its own strict validation in `_load_clean_profiles`.
    """
    path = Path(data_dir) / "profiles_raw.jsonl"
    if not path.exists():
        return None
    urls_by_school: dict[str, set[str]] = defaultdict(set)
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            school_id = record["school_id"]
            profile_url = record["profile_url"]
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
        urls_by_school[school_id].add(profile_url)
    return {school_id: len(urls) for school_id, urls in urls_by_school.items()}


# -- writing ----------------------------------------------------------------


def _unique_slug(school_id: str, used: set[str]) -> str:
    """`slugify(school_id)` for the output filename — defense in depth
    against a `school_id` that (unlike Stage 1's `School.slug == school_id`
    invariant) isn't already filename-safe. Idempotent on an already-slug
    id, so this is a no-op in the common case. A collision (two distinct
    school_ids slugifying to the same string) falls back to appending the
    raw school_id rather than silently overwriting one school's CSV with
    another's."""
    slug = slugify(school_id) or school_id
    if slug not in used:
        used.add(slug)
        return slug
    fallback = f"{slug}-{slugify(school_id)}-{len(used)}"
    used.add(fallback)
    return fallback


def _write_csv(path: Path, rows: list[Professor]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_COLUMNS)
        for row in rows:
            writer.writerow(_professor_row(row))


# A directory this stale is worth a line in the summary, not just a column.
_STALE_SOURCE_SHARE = 0.15


def _dead_cells(
    dead_counts: dict[str, tuple[int, int]] | None, school_id: str
) -> tuple[str, str]:
    """`(fetched, dead)` as CSV cells, both "unknown" when there is no raw
    data to read — never "0", which would assert a directory is current on
    the strength of a missing file."""
    if dead_counts is None:
        return "unknown", "unknown"
    entry = dead_counts.get(school_id)
    if entry is None:
        return "unknown", "unknown"
    fetched, dead = entry
    return str(fetched), str(dead)


def _bool_cell(value: bool | None) -> str:
    """"true"/"false"/"" — never "None", and never a bare empty string
    standing in for false. Unknown and not-faculty must stay distinguishable
    in the CSV, the same way `n/a` and an em dash are in the UI."""
    return "" if value is None else ("true" if value else "false")


def _professor_row(p: Professor) -> list[str]:
    """§4.4 column order. A `None` field becomes an empty CSV cell — never
    the string "None"/"null"/"nan" (the easiest way this dataset could
    start asserting things that aren't true)."""
    return [
        p.school_id,
        p.school_name,
        p.professor_name,
        _cell(p.title),
        _bool_cell(resolved_role(p)),
        _cell(p.department),
        _cell(p.email),
        _cell(p.phone),
        _cell(p.research_interests),
        p.profile_url,
        p.directory_url,
        str(p.extraction_confidence),
        p.extracted_at.isoformat(),
    ]


def _cell(value: str | None) -> str:
    return value if value is not None else ""


def _write_coverage_report(
    path: Path,
    by_school: dict[str, list[Professor]],
    kept_by_school: dict[str, list[Professor]],
    partial_school_ids: set[str],
    capped_school_ids: set[str],
    raw_counts: dict[str, int] | None,
    non_faculty_by_school: dict[str, int],
    dead_counts: dict[str, tuple[int, int]] | None,
) -> None:
    """A sibling report, not a §4.4 column: per-school row counts (both what
    made the CSV and what min_confidence excluded), the partial-coverage
    flag, the count excluded as administrators/staff, and the
    max_profiles_per_school-truncation flag, so a 17-of-400
    school (or a 100-of-several-hundred school) is visibly different from a
    complete one without lying about it inside the per-professor schema.
    `capped_at_limit` is `"unknown"` (never `"false"`) when `raw_counts` is
    `None` — i.e. `data/profiles_raw.jsonl` wasn't available to check."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(_COVERAGE_COLUMNS)
        for school_id in sorted(by_school):
            all_rows = by_school[school_id]
            kept_rows = kept_by_school.get(school_id, [])
            school_name = all_rows[0].school_name if all_rows else school_id
            is_partial = school_id in partial_school_ids
            is_capped = school_id in capped_school_ids
            capped_cell = "unknown" if raw_counts is None else ("true" if is_capped else "false")
            writer.writerow(
                [
                    school_id,
                    school_name,
                    len(kept_rows),
                    len(all_rows) - len(kept_rows) - non_faculty_by_school.get(school_id, 0),
                    non_faculty_by_school.get(school_id, 0),
                    *_dead_cells(dead_counts, school_id),
                    "true" if is_partial else "false",
                    capped_cell,
                    "true" if (is_partial or is_capped) else "false",
                ]
            )
