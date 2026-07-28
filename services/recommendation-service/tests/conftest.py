import pytest

from app.llm import Review
from app.schemas import Profile, ScoredUniversity


@pytest.fixture
def profile() -> Profile:
    return Profile(gpa=3.8, sat=1400, mbti="ENFP", intended_major="Computer Science")


def scored(ids_scores):
    return [
        ScoredUniversity(university_id=i, score=s, components={"academic": s})
        for i, s in ids_scores
    ]


@pytest.fixture
def names():
    return {"u1": "Alpha", "u2": "Beta", "u3": "Gamma", "u4": "Delta"}


class StaticLLM:
    """Returns the same raw review every iteration."""

    def __init__(self, keep_ids=None, confidence=0.5, weight_feedback=None, notes=None):
        self._review = Review(
            keep_ids=keep_ids or [],
            confidence=confidence,
            weight_feedback=weight_feedback or {},
            notes=notes or {},
        )

    def review(self, profile, scored, iteration):
        return Review(**self._review)


class FlipLLM:
    """Never converges: empty keep, low confidence, and flips weights each turn
    so the ranking keeps changing (defeats R1, R2, R3 until the R4 cap)."""

    def review(self, profile, scored, iteration):
        factor = 0.5 if iteration % 2 == 0 else 1.5
        return Review(keep_ids=[], confidence=0.1,
                      weight_feedback={"academic": factor}, notes={})
