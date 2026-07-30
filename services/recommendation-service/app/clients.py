"""Client to the deterministic scoring-service and the rank_fn factory."""
from __future__ import annotations

import os
from collections.abc import Callable

import httpx

from .schemas import Profile, ScoredUniversity, University

SCORING_URL = os.environ.get("SCORING_SERVICE_URL", "http://scoring-service:8001")


def make_rank_fn(
    profile: Profile,
    universities: list[University],
    client: httpx.Client | None = None,
    url: str = SCORING_URL,
) -> Callable[[dict[str, float]], list[ScoredUniversity]]:
    """Return a rank_fn(weight_feedback) that calls scoring-service POST /rank."""
    unis = [u.model_dump() for u in universities]

    def rank_fn(weight_feedback: dict[str, float]) -> list[ScoredUniversity]:
        payload = {
            "profile": profile.model_dump(),
            "weight_feedback": weight_feedback,
            "universities": unis,
        }
        owns = client is None
        c = client or httpx.Client(timeout=10.0)
        try:
            resp = c.post(f"{url}/rank", json=payload)
            resp.raise_for_status()
            data = resp.json()
        finally:
            if owns:
                c.close()
        return [ScoredUniversity(**s) for s in data["scores"]]

    return rank_fn


def make_classify_fn(
    client: httpx.Client | None = None,
    url: str = SCORING_URL,
) -> Callable[[str, str, str | None], list[str]]:
    """Return classify(name, kind, description) calling scoring-service POST /classify.

    scoring-service owns the pattern table; forwarding keeps one implementation
    rather than a second copy that could silently diverge from the scorer.
    """

    def classify(name: str, kind: str, description: str | None) -> list[str]:
        payload = {"name": name, "kind": kind, "description": description}
        owns = client is None
        c = client or httpx.Client(timeout=10.0)
        try:
            resp = c.post(f"{url}/classify", json=payload)
            resp.raise_for_status()
            data = resp.json()
        finally:
            if owns:
                c.close()
        return list(data["subjects"])

    return classify
