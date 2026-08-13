"""Candidate universities source.

Reads from Postgres when DATABASE_URL is set (the data-pipeline loads it there);
otherwise falls back to the bundled seed so the service and its tests run fully
offline.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from .schemas import University

_SEED = Path(__file__).with_name("seed_universities.json")

logger = logging.getLogger(__name__)

_cache: list[University] | None = None


def load_universities() -> list[University]:
    """The catalog, loaded once and cached.

    A fallback to the bundled seed is deliberately **not** cached. Postgres
    passes its healthcheck before `data-pipeline/load.py` has run, so the first
    request can land on an unseeded table; that returns an empty list rather
    than raising, and caching it would serve zero schools — silently, with no
    error — for the life of the process. An empty catalog is treated as a
    failed load: log it, serve the seed, and retry the database next call.
    """
    global _cache
    if _cache is not None:
        return _cache

    url = os.environ.get("DATABASE_URL")
    if not url:
        _cache = _load_from_seed()
        return _cache

    try:
        catalog = _load_from_db(url)
    except Exception as exc:
        logger.warning("catalog load failed (%s); serving the bundled seed instead", exc)
        return _load_from_seed()

    if not catalog:
        logger.warning(
            "catalog query returned 0 universities - is the database seeded? "
            "serving the bundled seed instead",
        )
        return _load_from_seed()

    _cache = catalog
    return _cache


def reset_cache() -> None:
    """Drop the cached catalog. For tests, and for a reload after seeding."""
    global _cache
    _cache = None


def _load_from_seed() -> list[University]:
    raw = json.loads(_SEED.read_text())
    return [University(**row) for row in raw]


def _load_from_db(url: str) -> list[University]:  # pragma: no cover - needs Postgres
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(url, row_factory=dict_row) as conn:
        rows = conn.execute(
            "SELECT id, unitid, name, country, location, state, region, setting, type, "
            "avg_gpa, avg_sat, acceptance_rate, net_price, sticker_tuition, "
            "tuition_in_state, programs, notable_faculty, "
            "enrollment, size, majors, culture, population, url, "
            "net_price_calculator_url, details, provenance FROM universities"
        ).fetchall()
    return [University(**row) for row in rows]


def in_scope(
    universities: list[University],
    scope: str,
    institution_type: str | None = None,
) -> list[University]:
    """Restrict candidates by country scope and institution type.

    Both are hard filters applied before ranking so a requested top_k is still
    filled. An unrecognised scope returns everything rather than nothing.
    """
    if scope == "usa":
        kept = [u for u in universities if u.country == "USA"]
    elif scope == "international":
        kept = [u for u in universities if u.country != "USA"]
    else:
        kept = list(universities)
    if institution_type is not None:
        kept = [u for u in kept if u.type == institution_type]
    return kept


def by_id(universities: list[University]) -> dict[str, University]:
    """Index by id. The loop needs whole records, not just names, to emit the
    per-result university summary and admit_tier."""
    return {u.id: u for u in universities}
