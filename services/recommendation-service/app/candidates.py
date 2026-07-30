"""Candidate universities source.

Reads from Postgres when DATABASE_URL is set (the data-pipeline loads it there);
otherwise falls back to the bundled seed so the service and its tests run fully
offline.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

from .schemas import University

_SEED = Path(__file__).with_name("seed_universities.json")


@lru_cache(maxsize=1)
def load_universities() -> list[University]:
    url = os.environ.get("DATABASE_URL")
    if url:
        try:
            return _load_from_db(url)
        except Exception:  # pragma: no cover - offline fallback
            pass
    return _load_from_seed()


def _load_from_seed() -> list[University]:
    raw = json.loads(_SEED.read_text())
    return [University(**row) for row in raw]


def _load_from_db(url: str) -> list[University]:  # pragma: no cover - needs Postgres
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(url, row_factory=dict_row) as conn:
        rows = conn.execute(
            "SELECT id, unitid, name, country, location, region, setting, type, "
            "avg_gpa, avg_sat, acceptance_rate, net_price, sticker_tuition, "
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
