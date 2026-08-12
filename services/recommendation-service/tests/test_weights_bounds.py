"""The weight ceiling has to hold at this boundary too.

The gateway talks only to this service, so `profile.weights` arrives here first.
scoring-service enforces the same bound (its tests/test_weights_bounds.py), but
a mirror that validated less than its sibling would let an absurd weight through
to a service that then rejects it - a 502 where a 422 is the honest answer.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.main as main
from app.schemas import ScoredUniversity, Weights

client = TestClient(main.app)


def _fake_rank_fn_factory(profile, universities, *a, **k):
    """No unit test opens a socket; the ranking itself is scoring-service's."""

    def rank_fn(weight_feedback):
        return [
            ScoredUniversity(university_id=u.id, score=0.5, components={"cost": 0.5})
            for u in universities
        ]

    return rank_fn


def test_a_weight_may_be_the_whole_share():
    assert Weights(cost=1.0).cost == 1.0


def test_a_weight_above_one_is_rejected():
    with pytest.raises(ValidationError):
        Weights(cost=1.0001)


def test_the_endpoint_rejects_an_absurd_weight():
    response = client.post(
        "/recommend",
        json={
            "profile": {
                "gpa": 3.7,
                "intended_major": "Computer Science",
                "weights": {"cost": 999999},
            },
            "top_k": 3,
        },
    )

    assert response.status_code == 422


def test_the_endpoint_accepts_a_maxed_weight(monkeypatch):
    monkeypatch.setattr(main, "make_rank_fn", _fake_rank_fn_factory)
    response = client.post(
        "/recommend",
        json={
            "profile": {
                "gpa": 3.7,
                "intended_major": "Computer Science",
                "weights": {"cost": 1.0},
            },
            "top_k": 3,
        },
    )

    assert response.status_code == 200
