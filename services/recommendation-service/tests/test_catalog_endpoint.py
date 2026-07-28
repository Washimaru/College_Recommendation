"""GET /universities — the whole catalog, for the browse view.

Returned in one request so the client can search instantly without a round
trip per keystroke. Read-only: no scoring, no loop, no writes.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_returns_the_catalog():
    response = client.get("/universities")

    assert response.status_code == 200
    body = response.json()
    assert len(body["universities"]) > 0


def test_records_carry_what_the_browse_view_needs():
    uni = client.get("/universities").json()["universities"][0]

    for field in ("id", "name", "country", "location", "avg_gpa", "size", "majors", "culture"):
        assert field in uni, f"missing {field}"


def test_preserves_honest_nulls_and_provenance():
    """Browse must be able to render the same n/a vs em-dash distinction."""
    unis = client.get("/universities").json()["universities"]

    assert any(u["avg_sat"] is None for u in unis)
    assert all("provenance" in u for u in unis)


def test_is_ordered_stably_by_id():
    ids = [u["id"] for u in client.get("/universities").json()["universities"]]

    assert ids == sorted(ids)
