"""Reach / Target / Safety classification.

Computed server-side, not in the browser: it is deterministic domain logic, so
it belongs with the rest of it and stays covered by these gates. Thresholds
inherited from the original UniMatch project's admitTier.

    d = university.avg_gpa - profile.gpa
    d >=  0.12 -> reach     (school's admitted average is above the student)
    d <= -0.12 -> safety    (student is above the school's average)
    otherwise  -> target
"""
from __future__ import annotations

from app.loop import admit_tier


def test_school_well_above_student_is_a_reach():
    assert admit_tier(student_gpa=3.5, school_avg_gpa=3.9) == "reach"


def test_school_well_below_student_is_a_safety():
    assert admit_tier(student_gpa=3.9, school_avg_gpa=3.4) == "safety"


def test_close_match_is_a_target():
    assert admit_tier(student_gpa=3.7, school_avg_gpa=3.7) == "target"


def test_boundaries_are_inclusive_at_twelve_hundredths():
    assert admit_tier(student_gpa=3.5, school_avg_gpa=3.62) == "reach"
    assert admit_tier(student_gpa=3.5, school_avg_gpa=3.38) == "safety"


def test_just_inside_the_boundary_is_a_target():
    assert admit_tier(student_gpa=3.5, school_avg_gpa=3.61) == "target"
    assert admit_tier(student_gpa=3.5, school_avg_gpa=3.39) == "target"


def test_no_student_gpa_yields_no_tier():
    """Without the student's GPA there is nothing to compare; null, not a guess."""
    assert admit_tier(student_gpa=None, school_avg_gpa=3.9) is None
