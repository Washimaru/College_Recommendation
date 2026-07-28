"""Deterministic weighted-rubric scoring.

Contract of determinism: no randomness, no clock, no LLM. The same RankRequest
always yields the same RankResponse (enforced by test_determinism).
"""
from __future__ import annotations

from .schemas import (
    CULTURE_AXES,
    Culture,
    CulturePrefs,
    Profile,
    RankRequest,
    RankResponse,
    ScoredUniversity,
    University,
)

# Default rubric weights. Overridable per-request via profile.weights and then
# multiplicatively adjusted by weight_feedback (already clamped by the loop).
DEFAULT_WEIGHTS: dict[str, float] = {
    "academic": 0.35,
    "cost": 0.20,
    "fit": 0.25,
    "culture": 0.20,
}


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _academic_fit(profile: Profile, uni: University) -> float:
    gpa_gap = (profile.gpa - uni.avg_gpa) / 4.0
    gpa_score = _clamp01(0.5 + gpa_gap)  # at/above average scores higher
    # Both sides must be present: the school's SAT is null for every non-US
    # school and every test-free US school, and is never derived from GPA.
    if profile.sat is not None and uni.avg_sat is not None:
        sat_gap = (profile.sat - uni.avg_sat) / 1200.0
        sat_score = _clamp01(0.5 + sat_gap)
        return round((gpa_score + sat_score) / 2.0, 6)
    return round(gpa_score, 6)


def _cost_fit(profile: Profile, uni: University) -> float:
    # Unknown price scores neutral, never free: an absent value must not make a
    # school look affordable.
    if uni.net_price is None:
        return 0.5
    cap = profile.preferences.max_tuition
    if cap is None:
        # No stated cap: mild preference for lower net price (60k reference).
        return round(_clamp01(1.0 - uni.net_price / 60000.0), 6)
    if uni.net_price <= cap:
        return 1.0
    over = (uni.net_price - cap) / max(cap, 1.0)
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


def culture_fit(prefs: CulturePrefs, culture: Culture) -> float:
    """Preference-weighted agreement over the six bipolar culture axes.

    Each axis contributes in proportion to how far the student moved it from
    centre, so untouched axes neither help nor hurt. Agreement is closeness,
    not dot product, because these axes are bipolar: wanting a competitive
    campus (0.0) and getting one (0.0) is a match, and cosine would score that
    identically to a total mismatch.

    Returns 0.5 when no preference is expressed at all.
    """
    total_importance = 0.0
    weighted = 0.0
    for axis in CULTURE_AXES:
        preference = getattr(prefs, axis)
        importance = abs(preference - 0.5) * 2
        if importance == 0.0:
            continue
        agreement = 1.0 - abs(preference - getattr(culture, axis))
        weighted += importance * agreement
        total_importance += importance

    if total_importance == 0.0:
        return 0.5
    return round(_clamp01(weighted / total_importance), 6)


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
        "culture": culture_fit(profile.culture_prefs, uni.culture),
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
