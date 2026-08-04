"""Extreme Reach / Reach / Target / Safety classification.

Computed server-side, not in the browser: it is deterministic domain logic, so
it belongs with the rest of it and stays covered by these gates. Thresholds
inherited from the original UniMatch project's admitTier, plus a new
selectivity-first tier from docs/superpowers/specs/
2026-08-03-gpa-scales-tiers-and-profiles-design.md.

    extreme_reach   acceptance_rate is not None and acceptance_rate <= 0.15
    reach           school_avg_gpa - student_gpa >=  0.12
    safety          school_avg_gpa - student_gpa <= -0.12
    target          otherwise

`extreme_reach` is checked first and is keyed on selectivity, not GPA: a null
acceptance_rate (every non-US school, and some US ones) must never manufacture
a tier, so it always falls through to the GPA rule.
"""
from __future__ import annotations

from app.loop import admit_tier


def test_school_well_above_student_is_a_reach():
    assert admit_tier(student_gpa=3.5, school_avg_gpa=3.9, acceptance_rate=0.5) == "reach"


def test_school_well_below_student_is_a_safety():
    assert admit_tier(student_gpa=3.9, school_avg_gpa=3.4, acceptance_rate=0.5) == "safety"


def test_close_match_is_a_target():
    assert admit_tier(student_gpa=3.7, school_avg_gpa=3.7, acceptance_rate=0.5) == "target"


def test_boundaries_are_inclusive_at_twelve_hundredths():
    assert admit_tier(student_gpa=3.5, school_avg_gpa=3.62, acceptance_rate=0.5) == "reach"
    assert admit_tier(student_gpa=3.5, school_avg_gpa=3.38, acceptance_rate=0.5) == "safety"


def test_just_inside_the_boundary_is_a_target():
    assert admit_tier(student_gpa=3.5, school_avg_gpa=3.61, acceptance_rate=0.5) == "target"
    assert admit_tier(student_gpa=3.5, school_avg_gpa=3.39, acceptance_rate=0.5) == "target"


def test_no_student_gpa_yields_no_tier():
    """Without the student's GPA there is nothing to compare; null, not a guess."""
    assert admit_tier(student_gpa=None, school_avg_gpa=3.9, acceptance_rate=0.5) is None


def test_low_acceptance_rate_is_extreme_reach_even_for_a_perfect_gpa():
    """At a 4% admit rate a 4.0 student is still rejected far more often than
    not. Calling that a 'target' because their GPA clears the average would be
    the most misleading thing this product could say."""
    assert admit_tier(student_gpa=4.0, school_avg_gpa=3.7, acceptance_rate=0.04) == "extreme_reach"


def test_extreme_reach_boundary_is_inclusive_at_fifteen_percent():
    assert admit_tier(student_gpa=3.9, school_avg_gpa=3.7, acceptance_rate=0.15) == "extreme_reach"


def test_just_above_fifteen_percent_falls_through_to_gpa_rule():
    assert admit_tier(student_gpa=3.7, school_avg_gpa=3.75, acceptance_rate=0.16) == "target"


def test_null_acceptance_rate_never_fires_extreme_reach():
    """Null is the normal case for every non-US school and some US ones. An
    absent rate must not manufacture a tier - it falls through to the GPA
    rule exactly as if the check never existed."""
    assert admit_tier(student_gpa=3.5, school_avg_gpa=3.9, acceptance_rate=None) == "reach"
    assert admit_tier(student_gpa=3.9, school_avg_gpa=3.4, acceptance_rate=None) == "safety"
    assert admit_tier(student_gpa=3.7, school_avg_gpa=3.7, acceptance_rate=None) == "target"


def test_extreme_reach_precedence_over_safety():
    """A hyper-selective school where the student's GPA happens to clear the
    average is still an extreme reach, not a safety - selectivity wins."""
    assert admit_tier(student_gpa=4.0, school_avg_gpa=3.5, acceptance_rate=0.05) == "extreme_reach"
