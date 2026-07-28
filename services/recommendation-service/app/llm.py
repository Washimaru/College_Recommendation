"""LLM interface + deterministic MockLLM.

Safety is NOT delegated to the model. Whatever the LLM returns is passed through
`loop.sanitize_review` before it can affect the result. The MockLLM keeps unit
tests offline and deterministic.
"""
from __future__ import annotations

from typing import Protocol

from .schemas import Profile, ScoredUniversity


class Review(dict):
    """Raw, UNTRUSTED review payload. Keys: keep_ids, confidence,
    weight_feedback, notes. Must go through sanitize_review before use."""


class LLM(Protocol):
    def review(
        self, profile: Profile, scored: list[ScoredUniversity], iteration: int
    ) -> Review: ...


class MockLLM:
    """Deterministic stand-in. Agrees with the scorer's top-k and grows more
    confident each iteration, so a normal run converges quickly."""

    def __init__(self, top_k: int = 5, base_confidence: float = 0.6) -> None:
        self.top_k = top_k
        self.base_confidence = base_confidence

    def review(
        self, profile: Profile, scored: list[ScoredUniversity], iteration: int
    ) -> Review:
        keep = [s.university_id for s in scored[: self.top_k]]
        confidence = min(1.0, self.base_confidence + 0.15 * iteration)
        notes = {
            s.university_id: (
                f"Strong on {max(s.components, key=s.components.get)} "
                f"(score {s.score:.2f})."
            )
            for s in scored[: self.top_k]
        }
        return Review(
            keep_ids=keep,
            confidence=confidence,
            weight_feedback={},
            notes=notes,
        )
