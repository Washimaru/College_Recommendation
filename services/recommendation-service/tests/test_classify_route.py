"""The route forwards to scoring-service, which owns the pattern table.

The forwarding function is injected, so these tests never open a socket - the
same discipline `rank_fn` follows.
"""
from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.clients import make_classify_fn
from app.main import app, get_classify_fn


@pytest.fixture
def client():
    calls: list[tuple[str, str, str | None]] = []

    def fake(name: str, kind: str, description: str | None) -> list[str]:
        calls.append((name, kind, description))
        return ["Computer Science", "Engineering"]

    app.dependency_overrides[get_classify_fn] = lambda: fake
    yield TestClient(app), calls
    app.dependency_overrides.clear()


def test_returns_the_subjects_from_scoring_service(client):
    test_client, _ = client

    response = test_client.post(
        "/activities/classify", json={"name": "FIRST Robotics", "kind": "competition"}
    )

    assert response.status_code == 200
    assert response.json()["subjects"] == ["Computer Science", "Engineering"]


def test_forwards_the_description(client):
    """The fake classifier stands in for scoring-service, so this only proves
    the route passes the description through - it does not depend on real
    pattern matching, and the description string need not match anything."""
    test_client, calls = client

    test_client.post(
        "/activities/classify",
        json={"name": "Science Bowl", "kind": "competition", "description": "built a rover"},
    )

    assert calls == [("Science Bowl", "competition", "built a rover")]


def test_name_is_required(client):
    test_client, _ = client

    assert test_client.post("/activities/classify", json={"kind": "club"}).status_code == 422


def test_an_unreachable_scorer_is_a_502_not_a_crash(client):
    """Recognition is advisory; the UI degrades. It must not surface a 500."""
    test_client, _ = client

    def broken(name: str, kind: str, description: str | None) -> list[str]:
        raise httpx.ConnectError("scoring-service is down")

    app.dependency_overrides[get_classify_fn] = lambda: broken

    response = test_client.post("/activities/classify", json={"name": "robotics", "kind": "club"})

    assert response.status_code == 502


def test_the_client_posts_to_the_scoring_endpoint():
    """Guards the URL and payload shape without a live service.

    The `.replace(" ", "")` in the original brief draft stripped the space out
    of "jazz band" itself, making the substring assertion impossible to
    satisfy against any body - httpx's default json encoding already emits
    compact `key:value` pairs with no space after the colon, so no stripping
    is needed at all. Only the assertion was corrected.
    """
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.read().decode()
        return httpx.Response(200, json={"subjects": ["Music"]})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http:
        classify = make_classify_fn(client=http, url="http://scoring:8001")
        assert classify("jazz band", "arts", None) == ["Music"]

    assert seen["url"] == "http://scoring:8001/classify"
    assert '"name":"jazz band"' in str(seen["body"])
