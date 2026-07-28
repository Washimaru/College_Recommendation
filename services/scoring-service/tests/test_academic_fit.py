"""Academic fit must peak where the student matches the school.

Regression: a linear ramp (0.5 + gap/4) rewards overmatching without limit, so
for a 3.8 GPA student a school averaging 3.2 scored 0.650 while MIT at 3.95
scored 0.462. Academic carries the heaviest weight (0.35), so that inverted the
whole ranking toward safety schools.
"""
from __future__ import annotations

from app.schemas import Culture, Profile, University
from app.scoring import _academic_fit

NEUTRAL = Culture(collab=0.5, quirky=0.5, idealist=0.5, research=0.5, spirit=0.5, seminar=0.5)


def _uni(avg_gpa: float, avg_sat: int | None = None) -> University:
    return University(
        id=f"u{avg_gpa}", name="U", country="USA", location="CA",
        avg_gpa=avg_gpa, avg_sat=avg_sat, size="medium", majors=[], culture=NEUTRAL,
    )


def _student(gpa: float = 3.8, sat: int | None = None) -> Profile:
    return Profile(gpa=gpa, sat=sat, intended_major="Computer Science")


def test_matched_school_beats_badly_overmatched_school():
    """The core regression. A 3.8 student fits a 3.8 school better than a 3.2."""
    matched = _academic_fit(_student(), _uni(3.8))
    overmatched = _academic_fit(_student(), _uni(3.2))

    assert matched > overmatched


def test_matched_school_beats_far_reach():
    matched = _academic_fit(_student(), _uni(3.8))
    reach = _academic_fit(_student(), _uni(4.0))

    assert matched > reach


def test_score_decreases_monotonically_as_school_falls_below_student():
    """No plateau or reversal: further below the student is steadily worse."""
    scores = [_academic_fit(_student(), _uni(g)) for g in (3.8, 3.6, 3.4, 3.2, 3.0)]

    assert scores == sorted(scores, reverse=True)


def test_slight_reach_scores_close_to_matched():
    """A modest reach should still be attractive, not written off."""
    matched = _academic_fit(_student(), _uni(3.8))
    slight_reach = _academic_fit(_student(), _uni(3.9))

    assert slight_reach > 0.7 * matched


def test_sat_agreement_also_peaks_at_match():
    matched = _academic_fit(_student(sat=1400), _uni(3.8, avg_sat=1400))
    overmatched = _academic_fit(_student(sat=1400), _uni(3.8, avg_sat=1000))

    assert matched > overmatched


def test_null_avg_sat_still_falls_back_to_gpa_only():
    """The honest-nulls behaviour must survive the reshape."""
    assert _academic_fit(_student(sat=1400), _uni(3.8, avg_sat=None)) == _academic_fit(
        _student(), _uni(3.8, avg_sat=None)
    )


def test_stays_within_unit_interval():
    for student_gpa in (0.0, 2.0, 3.5, 4.0):
        for school_gpa in (2.0, 3.0, 3.5, 4.0):
            score = _academic_fit(_student(gpa=student_gpa), _uni(school_gpa))
            assert 0.0 <= score <= 1.0
