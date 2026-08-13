"""Contract v2.0.0 shape tests.

MBTI is removed from Profile and replaced by self-reported culture preferences.
University gains nullable admissions fields, a required culture vector, and
provenance. See docs/superpowers/specs/2026-07-27-real-university-catalog-design.md
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import CONTRACT_VERSION, CulturePrefs, Profile, University


def test_contract_version_is_9():
    """v3.0.0 added activities and personality; v3.1.0 added country scope;
    v4.0.0 adds place and population fields and removes preferences.locations;
    v5.0.0 adds Profile.gpa_weighted and the extreme_reach admit tier;
    v6.0.0 caps each profile.weights override at 1.0 and enforces the
    weight_feedback clamp here rather than trusting the caller;
    v7.0.0 adds University.tuition_in_state and University.programs;
    v8.0.0 adds University.state and Preferences.home_state, so an
    out-of-state applicant stops being quoted a resident's net price;
    v9.0.0 adds University.notable_faculty — named professors, with no
    contact details and no model in the chain that produced them."""
    assert CONTRACT_VERSION == "9.0.0"


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
    """Culture drives 18% of the score, so a school without it cannot be ranked."""
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


class TestContractV7:
    """v7.0.0 adds the two Phase 4 fields. Both are optional and default to
    None, so the bundled seed and every existing caller keep working."""

    def _uni(self, **overrides):
        base = dict(
            id="um", name="Michigan", country="USA", location="Ann Arbor, MI",
            region="Midwest", setting="suburban", type="Public",
            avg_gpa=3.8, size="large", majors=["Engineering"],
            culture={"collab": 0.5, "quirky": 0.5, "idealist": 0.5,
                     "research": 0.5, "spirit": 0.5, "seminar": 0.5},
        )
        return University(**{**base, **overrides})

    def test_in_state_tuition_is_carried(self):
        uni = self._uni(tuition_in_state=17736, sticker_tuition=60946)

        assert uni.tuition_in_state == 17736
        assert uni.sticker_tuition == 60946

    def test_in_state_tuition_defaults_to_unknown(self):
        assert self._uni().tuition_in_state is None

    def test_a_negative_tuition_is_rejected(self):
        with pytest.raises(ValidationError):
            self._uni(tuition_in_state=-1)

    def test_programs_carry_a_name_and_a_share(self):
        uni = self._uni(programs=[{"name": "Engineering", "share": 0.27}])

        assert uni.programs[0].name == "Engineering"
        assert uni.programs[0].share == 0.27

    def test_an_empty_program_list_is_not_the_same_as_unmeasured(self):
        """[] is "we looked and this school awards none of these"; None is
        "nobody measured". Only the first can support "does not offer X"."""
        assert self._uni(programs=[]).programs == []
        assert self._uni().programs is None

    def test_a_share_above_one_is_rejected(self):
        with pytest.raises(ValidationError):
            self._uni(programs=[{"name": "Engineering", "share": 1.5}])

    def test_a_program_needs_a_name(self):
        with pytest.raises(ValidationError):
            self._uni(programs=[{"share": 0.5}])


class TestNotableFacultyContract:
    """v9.0.0. The field publishes who a professor is, never how to reach them."""

    def _uni(self, **overrides):
        base = dict(
            id="mit", name="MIT", country="USA", location="Cambridge, MA", state="MA",
            region="Northeast", setting="urban", type="Private", avg_gpa=3.95,
            size="small", majors=["Engineering"],
            culture={"collab": 0.5, "quirky": 0.5, "idealist": 0.5,
                     "research": 0.5, "spirit": 0.5, "seminar": 0.5},
        )
        return University(**{**base, **overrides})

    def _person(self, **overrides):
        return {"name": "Noam Chomsky", "known_for": "American linguist",
                "fields": ["linguist"], "status": "current", "prominence": 178,
                "source": "wikipedia",
                "source_url": "https://en.wikipedia.org/wiki/Noam_Chomsky", **overrides}

    def test_a_professor_is_carried_with_their_source(self):
        uni = self._uni(notable_faculty=[self._person()])

        assert uni.notable_faculty[0].name == "Noam Chomsky"
        assert uni.notable_faculty[0].source_url.startswith("https://en.wikipedia.org/")

    def test_unsearched_and_searched_empty_are_different(self):
        assert self._uni().notable_faculty is None
        assert self._uni(notable_faculty=[]).notable_faculty == []

    def test_a_contact_detail_is_rejected_outright(self):
        """extra='forbid' is the guard: an email cannot reach this field by
        being added upstream and nobody noticing."""
        with pytest.raises(ValidationError):
            self._uni(notable_faculty=[self._person(email="noam@mit.edu")])

    def test_status_is_only_current_or_historical(self):
        with pytest.raises(ValidationError):
            self._uni(notable_faculty=[self._person(status="dead")])

    def test_a_professor_needs_a_source_to_check(self):
        person = self._person()
        del person["source_url"]
        with pytest.raises(ValidationError):
            self._uni(notable_faculty=[person])
