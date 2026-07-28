"""Writes to the `recommendations` table. This service is the sole owner of
those writes. No-op when DATABASE_URL is unset (offline/dev)."""
from __future__ import annotations

import json
import os

from .schemas import Profile, RecommendationResponse


def persist(profile: Profile, response: RecommendationResponse) -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        return
    _persist_db(url, profile, response)  # pragma: no cover - needs Postgres


def _persist_db(  # pragma: no cover
    url: str, profile: Profile, response: RecommendationResponse
) -> None:
    import psycopg

    with psycopg.connect(url) as conn:
        conn.execute(
            "INSERT INTO recommendations (profile, results, confidence, stop_reason) "
            "VALUES (%s, %s, %s, %s)",
            (
                json.dumps(profile.model_dump()),
                json.dumps([r.model_dump() for r in response.results]),
                response.confidence,
                response.stop_reason,
            ),
        )
        conn.commit()
