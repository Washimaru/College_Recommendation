"""Contract v2.0.0 shape tests.

MBTI is removed from Profile and replaced by self-reported culture preferences.
University gains nullable admissions fields, a required culture vector, and
provenance. See docs/superpowers/specs/2026-07-27-real-university-catalog-design.md
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import CONTRACT_VERSION, CulturePrefs, Profile, University


def test_contract_version_is_5():
    """v3.0.0 added activities and personality; v3.1.0 added country scope;
    v4.0.0 adds place and population fields and removes preferences.locations;
    v5.0.0 adds Profile.gpa_weighted and the extreme_reach admit tier."""
    assert CONTRACT_VERSION == "5.0.0"


def test_profile_needs_no_mbti():
    profile = Profile(gpa=3.8, intended_major="Computer Science")

    assert profile.gpa == 3.8


def test_profile_rejects_mbti():
    """The field is gone; extra='forbid' must reject it rather than ignore it."""
    with pytest.raises(ValidationError):
        Profile(gpa=3.8, intended_major="Computer Science", mbti="ENFP")


def test_profile_gpa_weighted_is_optional():
    """Its absence changes nothing; unweighted gpa alone is still valid."""
    profile = Profile(gpa=3.8, intended_major="Computer Science")

    assert profile.gpa_weighted is None


def test_profile_accepts_gpa_weighted_up_to_five():
    profile = Profile(gpa=3.8, gpa_weighted=4.42, intended_major="Computer Science")

    assert profile.gpa_weighted == 4.42


def test_profile_rejects_gpa_weighted_above_five():
    with pytest.raises(ValidationError):
        Profile(gpa=3.8, gpa_weighted=5.01, intended_major="Computer Science")


def test_profile_rejects_negative_gpa_weighted():
    with pytest.raises(ValidationError):
        Profile(gpa=3.8, gpa_weighted=-0.1, intended_major="Computer Science")


def test_culture_prefs_default_to_centre():
    """A student who touches no slider expresses no preference."""
    prefs = CulturePrefs()

    assert prefs.model_dump() == {
        "collab": 0.5,
        "quirky": 0.5,
        "idealist": 0.5,
        "research": 0.5,
        "spirit": 0.5,
        "seminar": 0.5,
    }


def test_university_allows_null_admissions_fields():
    """Honest nulls: a school with no observed SAT is null, never derived."""
    uni = University(
        id="oxford", name="University of Oxford", country="UK", location="Oxford",
        region="International", setting="urban", type="Public",
        avg_gpa=3.9, avg_sat=None, acceptance_rate=None, net_price=None,
        size="medium", majors=["PPE"],
        culture={"collab": 0.5, "quirky": 0.8, "idealist": 0.6,
                 "research": 0.9, "spirit": 0.4, "seminar": 0.9},
    )

    assert uni.avg_sat is None
    assert uni.acceptance_rate is None


def test_university_requires_culture():
    """Culture drives 20% of the score, so a school without it cannot be ranked."""
    with pytest.raises(ValidationError):
        University(
            id="x", name="No Culture U", country="USA", location="CA",
            avg_gpa=3.5, size="small", majors=[],
        )


def test_university_carries_place_and_population():
    uni = University(
        id="mit", name="MIT", country="USA", location="Cambridge, MA",
        region="Northeast", setting="urban", type="Private",
        avg_gpa=3.95, size="small", majors=["Engineering"],
        culture={"collab": 0.7, "quirky": 0.85, "idealist": 0.55,
                 "research": 0.75, "spirit": 0.35, "seminar": 0.55},
        population={"international_share": 0.1028, "women_share": 0.4768,
                    "first_gen_share": 0.2585},
        url="web.mit.edu/",
    )

    assert uni.region == "Northeast"
    assert uni.setting == "urban"
    assert uni.population.international_share == 0.1028
    assert uni.net_price_calculator_url is None


def test_population_may_be_absent():
    uni = University(
        id="ox", name="Oxford", country="UK", location="Oxford",
        region="International", setting="urban", type="Public",
        avg_gpa=3.9, size="medium", majors=["PPE"],
        culture={"collab": 0.5, "quirky": 0.8, "idealist": 0.6,
                 "research": 0.9, "spirit": 0.4, "seminar": 0.9},
    )

    assert uni.population is None
