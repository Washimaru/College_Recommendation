"""Deterministic weighted-rubric scoring.

Contract of determinism: no randomness, no clock, no LLM. The same RankRequest
always yields the same RankResponse (enforced by test_determinism).
"""
from __future__ import annotations

import math
import re

from .schemas import (
    CULTURE_AXES,
    Culture,
    CulturePrefs,
    Personality,
    Profile,
    RankRequest,
    RankResponse,
    ScoredUniversity,
    University,
)

# Default rubric weights. Overridable per-request via profile.weights and then
# multiplicatively adjusted by weight_feedback (already clamped by the loop).
DEFAULT_WEIGHTS: dict[str, float] = {
    "academic": 0.28,
    "cost": 0.18,
    "fit": 0.18,
    "culture": 0.18,
    "activities": 0.10,
    "personality": 0.08,
}

# Activity keyword -> subject families a school may be strong in. Transparent
# and testable on purpose: the pairing of what a student does with what a
# school teaches is the signal, not the activity in isolation.
_ACTIVITY_SUBJECTS: list[tuple[str, tuple[str, ...]]] = [
    (r"robot|hackathon|coding|code|program|software|cyber|game dev|app",
     ("Computer Science", "Engineering", "Data Science", "Cybersecurity")),
    (r"science fair|olympiad|research|\blab\b|biology|chemistry|physics",
     ("Biology", "Chemistry", "Physics", "Neuroscience", "Research")),
    (r"math|calculus|number theory|putnam",
     ("Mathematics", "Math", "Statistics", "Data Science")),
    (r"debate|model un|\bmun\b|mock trial|speech|policy",
     ("Political Science", "International Relations", "Public Policy", "Law", "Philosophy")),
    (r"business|deca|entrepreneur|startup|invest|finance|marketing",
     ("Business", "Economics", "Finance", "Marketing", "Management")),
    (r"volunteer|service|nonprofit|charity|tutor|mentor|community",
     ("Social Work", "Public Health", "Education", "Sociology")),
    (r"music|band|orchestra|choir|jazz|piano|violin|composition",
     ("Music", "Music Performance", "Composition", "Performance")),
    (r"art|paint|draw|photograph|sculpt|design|ceramics",
     ("Studio Art", "Art", "Design", "Fine Arts", "Architecture")),
    (r"theat|drama|acting|film|dance|cinema",
     ("Drama", "Theatre", "Film", "Performance")),
    (r"writ|journal|newspaper|poetry|literary|yearbook",
     ("English", "Journalism", "Creative Writing", "Communications")),
    (r"environment|sustain|climate|ecology|conservation",
     ("Environmental Science", "Environmental Studies", "Geology")),
    (r"hospital|medic|nurs|pre-med|health|dental|pharma",
     ("Nursing", "Public Health", "Biology", "Health Sciences", "Medicine")),
    (r"engineer|build|maker|3d print|\bcad\b|rocket|car",
     ("Engineering", "Mechanical Engineering", "Electrical Engineering", "Architecture")),
    (r"sport|athlet|varsity|soccer|basketball|swim|track|tennis",
     ("Kinesiology", "Sport Management", "Health Sciences")),
]


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


# Academic fit peaks where the student matches the school and decays either
# side. A monotonic ramp would make an ever-larger overmatch score ever higher,
# which ranks safety schools above good matches - academic is the heaviest
# weight, so that inverts the entire result.
_GPA_SIGMA = 0.35
_SAT_SIGMA = 130.0
# Being at or slightly above the school's average is genuinely favourable, so a
# small bounded bonus applies on that side only.
_OVERMATCH_BONUS = 0.08
_OVERMATCH_BONUS_CAP = 0.5


def _peaked(gap: float, sigma: float) -> float:
    """1.0 when gap is 0, decaying as a gaussian either side. `gap` is
    student minus school, so positive means the student is above."""
    score = math.exp(-(gap * gap) / (2 * sigma * sigma))
    if gap >= 0:
        score += _OVERMATCH_BONUS * min(gap / sigma, _OVERMATCH_BONUS_CAP)
    return _clamp01(score)


def _academic_fit(profile: Profile, uni: University) -> float:
    gpa_score = _peaked(profile.gpa - uni.avg_gpa, _GPA_SIGMA)
    # Both sides must be present: the school's SAT is null for every non-US
    # school and every test-free US school, and is never derived from GPA.
    if profile.sat is not None and uni.avg_sat is not None:
        sat_score = _peaked(float(profile.sat - uni.avg_sat), _SAT_SIGMA)
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


def _place_match(preferred: list[str], actual: str) -> float:
    """1.0 when no preference is stated or the school matches one of them.

    Unstated scores 1.0 rather than neutral 0.5 on purpose: unlike the culture
    axes, which drop out of their average when untouched, this term is a fixed
    share of `fit`, so a neutral value would silently cost a student part of the
    dimension for a question they chose not to answer.
    """
    if not preferred:
        return 1.0
    return 1.0 if actual in preferred else 0.0


def _fit(profile: Profile, uni: University) -> float:
    """Major, region and setting. Campus size lives in the personality
    dimension; `location` is display-only and never scored."""
    major = 1.0 if profile.intended_major.lower() in {m.lower() for m in uni.majors} else 0.3
    region = _place_match(profile.preferences.regions, uni.region)
    setting = _place_match(profile.preferences.settings, uni.setting)
    return round(0.50 * major + 0.25 * region + 0.25 * setting, 6)


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


def activity_fit(activities: list, uni: University) -> float:
    """How well what the student does lines up with what the school teaches.

    Neutral (0.5) when no activities are given: silence must not be a penalty.
    """
    if not activities:
        return 0.5

    school_subjects = {major.lower() for major in uni.majors}
    hits = 0
    for activity in activities:
        text = f"{activity.name} {activity.kind}".lower()
        for pattern, subjects in _ACTIVITY_SUBJECTS:
            if re.search(pattern, text) and any(
                subject.lower() in school_subjects for subject in subjects
            ):
                hits += 1
                break

    # Diminishing returns: a third matching activity says less than the first.
    share = hits / len(activities)
    return round(_clamp01(0.5 + 0.5 * share), 6)


def personality_fit(personality: Personality, uni: University) -> float:
    """Match derived intensity and scale against school attributes the culture
    dimension does not use, so nothing is scored twice.

    Axes with no school data are skipped rather than guessed; when none are
    available the result is neutral.
    """
    parts: list[float] = []
    weights: list[float] = []

    if uni.acceptance_rate is not None:
        # Selectivity as a proxy for academic pressure.
        selectivity = 1.0 - uni.acceptance_rate
        importance = abs(personality.intensity - 0.5) * 2
        parts.append(1.0 - abs(personality.intensity - selectivity))
        weights.append(importance)

    if uni.enrollment is not None:
        # 25k undergraduates is treated as the top of the scale.
        scale = _clamp01(uni.enrollment / 25_000)
        importance = abs(personality.scale - 0.5) * 2
        parts.append(1.0 - abs(personality.scale - scale))
        weights.append(importance)

    total = sum(weights)
    if total == 0:
        return 0.5
    return round(
        _clamp01(sum(p * w for p, w in zip(parts, weights, strict=True)) / total), 6
    )


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
        "activities": activity_fit(profile.activities, uni),
        "personality": personality_fit(profile.personality, uni),
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
