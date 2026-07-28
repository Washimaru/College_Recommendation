"""Deterministic weighted-rubric scoring.

Contract of determinism: no randomness, no clock, no LLM. The same RankRequest
always yields the same RankResponse (enforced by test_determinism).
"""
from __future__ import annotations

from .schemas import Profile, RankRequest, RankResponse, ScoredUniversity, University

# Default rubric weights. Overridable per-request via profile.weights and then
# multiplicatively adjusted by weight_feedback (already clamped by the loop).
DEFAULT_WEIGHTS: dict[str, float] = {
    "academic": 0.35,
    "cost": 0.20,
    "fit": 0.25,
    "personality": 0.20,
}

# MBTI -> trait priors. Each letter nudges the size the student is predicted to
# thrive in. Deterministic lookup only.
_SIZE_ORDER = {"small": 0.0, "medium": 0.5, "large": 1.0}
_MBTI_SIZE_PREF = {"E": 1.0, "I": 0.0}  # extraversion -> larger campuses
_MBTI_STRUCTURE_PREF = {"J": 0.0, "P": 1.0}  # judging -> more selective/structured


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _academic_fit(profile: Profile, uni: University) -> float:
    gpa_gap = (profile.gpa - uni.avg_gpa) / 4.0
    gpa_score = _clamp01(0.5 + gpa_gap)  # at/above average scores higher
    if profile.sat is not None:
        sat_gap = (profile.sat - uni.avg_sat) / 1200.0
        sat_score = _clamp01(0.5 + sat_gap)
        return round((gpa_score + sat_score) / 2.0, 6)
    return round(gpa_score, 6)


def _cost_fit(profile: Profile, uni: University) -> float:
    cap = profile.preferences.max_tuition
    if cap is None:
        # No stated cap: mild preference for lower tuition (60k reference).
        return round(_clamp01(1.0 - uni.tuition / 60000.0), 6)
    if uni.tuition <= cap:
        return 1.0
    over = (uni.tuition - cap) / max(cap, 1.0)
    return round(_clamp01(1.0 - over), 6)


def _fit(profile: Profile, uni: University) -> float:
    major = 1.0 if profile.intended_major.lower() in {m.lower() for m in uni.majors} else 0.3
    size = 1.0
    if profile.preferences.preferred_size is not None:
        size = 1.0 if profile.preferences.preferred_size == uni.size else 0.4
    loc = 1.0
    if profile.preferences.locations:
        loc = 1.0 if uni.location in profile.preferences.locations else 0.4
    return round((0.5 * major + 0.25 * size + 0.25 * loc), 6)


def _personality_fit(profile: Profile, uni: University) -> float:
    size_pref = _MBTI_SIZE_PREF[profile.mbti[0]]
    size_val = _SIZE_ORDER[uni.size]
    size_match = 1.0 - abs(size_pref - size_val)
    structure_pref = _MBTI_STRUCTURE_PREF[profile.mbti[3]]
    # Structured students align with more selective schools (low acceptance rate).
    selectivity = 1.0 - uni.acceptance_rate
    structure_match = 1.0 - abs(structure_pref - selectivity)
    return round(_clamp01(0.6 * size_match + 0.4 * structure_match), 6)


def _resolve_weights(profile: Profile, weight_feedback: dict[str, float]) -> dict[str, float]:
    weights = dict(DEFAULT_WEIGHTS)
    if profile.weights is not None:
        for key, val in profile.weights.model_dump(exclude_none=True).items():
            weights[key] = val
    for key, factor in weight_feedback.items():
        if key in weights:
            weights[key] = weights[key] * factor
    return weights


def score_one(profile: Profile, uni: University, weights: dict[str, float]) -> ScoredUniversity:
    components = {
        "academic": _academic_fit(profile, uni),
        "cost": _cost_fit(profile, uni),
        "fit": _fit(profile, uni),
        "personality": _personality_fit(profile, uni),
    }
    total_w = sum(weights[k] for k in components) or 1.0
    raw = sum(weights[k] * components[k] for k in components) / total_w
    return ScoredUniversity(
        university_id=uni.id,
        score=round(_clamp01(raw), 6),
        components=components,
    )


def rank(request: RankRequest) -> RankResponse:
    weights = _resolve_weights(request.profile, request.weight_feedback)
    scored = [score_one(request.profile, uni, weights) for uni in request.universities]
    # Deterministic ordering: descending score, then ascending university_id.
    scored.sort(key=lambda s: (-s.score, s.university_id))
    return RankResponse(scores=scored)
