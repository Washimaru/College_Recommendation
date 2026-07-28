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
            "SELECT id, unitid, name, country, location, avg_gpa, avg_sat, "
            "acceptance_rate, net_price, sticker_tuition, enrollment, size, "
            "majors, culture, provenance FROM universities"
        ).fetchall()
    return [University(**row) for row in rows]


def names_map(universities: list[University]) -> dict[str, str]:
    return {u.id: u.name for u in universities}
