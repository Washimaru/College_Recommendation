"""Stage 1 — Load & Filter (§6 Stage 1).

**Adapted per the banner at the top of docs/FACULTY_PIPELINE.md.** The plan's
Stage 1 reads `school_details.json` directly; in this repo that file holds
only detail *sections* (academics, admissions, faculty, research…) keyed by
school id — no country, no state, no homepage. Those fields live in the
catalog (`data-pipeline/out/universities.json`, `config.input_path`), so this
stage:

1. reads the catalog and keeps US schools (§6 step 2's detection ladder:
   explicit `country` field first, then `state` in the 50 + DC, then a
   `.edu` homepage as a weak signal — logging low-confidence keeps);
2. left-joins `school_details.json` (`config.details_path`) by school id for
   the `source_fields` passthrough (§4.1). A school with no details entry is
   still valid, with empty passthrough — that's the common case.

Writes `data/schools.jsonl`, deduped by slug, sorted for byte-identical
re-runs on unchanged input. Not checkpointed per-item (§9 lists `discover`/
`crawl`/`extract` as the checkpointed stages) — this stage has no per-school
network call, so it just overwrites its output deterministically each run.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..config import Config
from ..models import School, StageSummary
from ..services.checkpoint import CheckpointStore

STAGE_NAME = "load_filter"

# 50 states + DC, per §6 step 2's detection ladder.
_US_STATES = frozenset(
    {
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
        "DC",
    }
)  # fmt: skip

# Catalog `location` is "City, ST" for US schools (§ input adaptation).
_LOCATION_RE = re.compile(r"^(?P<city>.*),\s*(?P<state>[A-Za-z]{2})\s*$")

_US_COUNTRY_VALUES = frozenset({"USA", "US", "UNITED STATES", "UNITED STATES OF AMERICA"})


class LoadFilterError(RuntimeError):
    """Fatal Stage 1 error (bad/missing input) — not a per-item failure."""


def run(
    config: Config,
    checkpoint: CheckpointStore,  # unused; see module docstring
    logger: logging.Logger,
    *,
    dry_run: bool = False,
) -> StageSummary:
    """Load `config.input_path` (the catalog), filter to U.S. schools, join
    `config.details_path` for passthrough, and write `data/schools.jsonl`.

    `dry_run=True` runs the full plan (read, filter, normalize) and returns
    the summary that *would* be written, without touching disk — used by the
    CLI's global `--dry-run` flag.
    """
    started_at = datetime.now(UTC)
    catalog = _load_catalog(config.input_path)
    details = _load_details(config.details_path, logger)

    schools_by_slug: dict[str, School] = {}
    notes: list[str] = []
    skipped = 0
    low_confidence_keeps = 0
    missing_homepage = 0
    duplicate_slugs = 0

    for record in catalog:
        school_id = record.get("id")
        if not school_id:
            skipped += 1
            logger.warning(
                "catalog record with no id skipped: %r",
                record,
                extra={"stage": STAGE_NAME},
            )
            continue

        is_us, confidence = _detect_us(record)
        if not is_us:
            skipped += 1
            continue
        if confidence == "low":
            low_confidence_keeps += 1
            logger.warning(
                "low-confidence US keep for %s (no explicit country field)",
                school_id,
                extra={"stage": STAGE_NAME, "school_id": school_id},
            )

        homepage = _normalize_homepage(record.get("url"))
        if homepage is None:
            missing_homepage += 1
            skipped += 1
            logger.warning(
                "school %s has no homepage (url) in the catalog; dropped",
                school_id,
                extra={"stage": STAGE_NAME, "school_id": school_id},
            )
            continue

        state = _parse_state(record.get("location"), logger, school_id)
        control = _normalize_control(record.get("type"))
        source_fields = details.get(school_id, {})

        school = School(
            school_id=school_id,
            name=record.get("name") or school_id,
            slug=school_id,  # already a slug in this catalog (verified, §input adaptation)
            country="US",
            state=state,
            homepage=homepage,
            control=control,
            source_fields=source_fields,
        )

        if school.slug in schools_by_slug:
            duplicate_slugs += 1
            skipped += 1
            logger.warning(
                "duplicate slug %s; keeping first occurrence",
                school.slug,
                extra={"stage": STAGE_NAME, "school_id": school_id},
            )
            continue
        schools_by_slug[school.slug] = school

    ordered = sorted(schools_by_slug.values(), key=lambda s: s.slug)

    if low_confidence_keeps:
        notes.append(f"{low_confidence_keeps} school(s) kept on a low-confidence US signal")
    if missing_homepage:
        notes.append(f"{missing_homepage} school(s) dropped for missing homepage")
    if duplicate_slugs:
        notes.append(f"{duplicate_slugs} duplicate slug(s) collapsed to first occurrence")
    with_details = sum(1 for s in ordered if s.source_fields)
    notes.append(f"{with_details}/{len(ordered)} kept schools have details passthrough")

    if not dry_run:
        _write_jsonl(Path(config.data_dir) / "schools.jsonl", ordered)

    return StageSummary(
        stage=STAGE_NAME,
        processed=len(ordered),
        skipped=skipped,
        failed=0,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        notes=notes,
    )


# -- loading -----------------------------------------------------------


def _load_catalog(path: str | Path) -> list[dict[str, Any]]:
    catalog_path = Path(path)
    if not catalog_path.exists():
        raise LoadFilterError(
            f"catalog not found at {catalog_path}. It is a gitignored build artifact — "
            "regenerate it with: cd data-pipeline && .venv/bin/python build_catalog.py"
        )
    raw = _read_json(catalog_path)
    if not isinstance(raw, list):
        raise LoadFilterError(f"{catalog_path}: expected a JSON array of school records")
    return raw


def _load_details(path: str | Path, logger: logging.Logger) -> dict[str, dict[str, Any]]:
    details_path = Path(path)
    if not details_path.exists():
        # Supplementary passthrough, not the primary input: missing just
        # means every school gets an empty source_fields, not a fatal error.
        logger.warning(
            "details file not found at %s; proceeding with empty source_fields passthrough",
            details_path,
            extra={"stage": STAGE_NAME},
        )
        return {}
    raw = _read_json(details_path)
    if not isinstance(raw, dict):
        raise LoadFilterError(f"{details_path}: expected a JSON object keyed by school id")
    return raw


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LoadFilterError(f"{path}: malformed JSON ({exc})") from exc


# -- filtering & normalization -------------------------------------------------


def _detect_us(record: dict[str, Any]) -> tuple[bool, str]:
    """§6 step 2's detection ladder. Returns (is_us, confidence), confidence
    being "high" (explicit signal either way) or "low" (state/`.edu` fallback
    only — must be logged by the caller)."""
    country = (record.get("country") or "").strip()
    if country:
        return country.upper() in _US_COUNTRY_VALUES, "high"

    location = record.get("location") or ""
    match = _LOCATION_RE.match(location.strip())
    if match and match.group("state").upper() in _US_STATES:
        return True, "low"

    homepage = (record.get("url") or "").strip().lower()
    if homepage and _looks_edu(homepage):
        return True, "low"

    return False, "high"


def _looks_edu(homepage: str) -> bool:
    without_scheme = re.sub(r"^https?://", "", homepage)
    host = without_scheme.split("/", 1)[0]
    return host == "edu" or host.endswith(".edu")


def _parse_state(location: Any, logger: logging.Logger, school_id: str) -> str | None:
    if not location:
        return None
    match = _LOCATION_RE.match(str(location).strip())
    if not match:
        logger.warning(
            "school %s: location %r doesn't match 'City, ST'; state left blank",
            school_id,
            location,
            extra={"stage": STAGE_NAME, "school_id": school_id},
        )
        return None
    return match.group("state").upper()


def _normalize_homepage(url: Any) -> str | None:
    if not url:
        return None
    url = str(url).strip()
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"https://{url}"


def _normalize_control(control_type: Any) -> str | None:
    if not control_type:
        return None
    text = str(control_type).strip()
    return text.lower() or None


# -- output --------------------------------------------------------------


def _write_jsonl(path: Path, schools: list[School]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [school.model_dump_json() for school in schools]
    # Trailing newline after the last line too, for a stable byte-identical
    # file across re-runs (and well-formed JSONL by convention).
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
