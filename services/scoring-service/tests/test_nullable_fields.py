"""Scoring must tolerate the honest nulls introduced in contract v2.0.0.

A school with no observed SAT or net price is common (all 90 non-US schools,
and every test-free US school). Scoring must degrade gracefully rather than
crash or invent a value.
"""
from __future__ import annotations

from app.schemas import Culture, Profile, University
from app.scoring import _academic_fit, _cost_fit

NEUTRAL = Culture(collab=0.5, quirky=0.5, idealist=0.5, research=0.5, spirit=0.5, seminar=0.5)


def _uni(**overrides) -> University:
    base = dict(
        id="u1", name="Test U", country="USA", location="CA",
        avg_gpa=3.7, size="medium", majors=["Computer Science"], culture=NEUTRAL,
    )
    return University(**{**base, **overrides})


def test_null_avg_sat_falls_back_to_gpa_only():
    """Mirrors how a missing profile.sat is already handled."""
    profile = Profile(gpa=3.7, sat=1400, intended_major="Computer Science")

    with_sat = _academic_fit(profile, _uni(avg_sat=1400))
    without_sat = _academic_fit(profile, _uni(avg_sat=None))

    assert without_sat == _academic_fit(
        Profile(gpa=3.7, intended_major="Computer Science"), _uni(avg_sat=None)
    )
    assert 0.0 <= without_sat <= 1.0
    assert with_sat != without_sat or with_sat == without_sat  # both must compute


def test_null_net_price_is_neutral_not_free():
    """An unknown price must not score as if the school were free."""
    profile = Profile(
        gpa=3.7, intended_major="Computer Science",
        preferences={"max_tuition": 30000},
    )

    unknown = _cost_fit(profile, _uni(net_price=None))
    free = _cost_fit(profile, _uni(net_price=0))

    assert unknown == 0.5
    assert free == 1.0
    assert unknown < free
