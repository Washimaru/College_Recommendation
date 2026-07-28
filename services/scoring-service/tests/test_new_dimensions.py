"""Contract v3.0.0 adds two scored dimensions.

    activities   what the student does  ->  what the school is strong in
    personality  derived intensity/scale ->  selectivity / enrollment

Both are self-reported. The personality dimension deliberately scores against
school attributes the culture dimension does not touch, so one signal is never
counted twice.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import Activity, Culture, Personality, Profile, University
from app.scoring import DEFAULT_WEIGHTS, activity_fit, personality_fit

NEUTRAL = Culture(collab=0.5, quirky=0.5, idealist=0.5, research=0.5, spirit=0.5, seminar=0.5)


def _uni(**over) -> University:
    base = dict(
        id="u1", name="U", country="USA", location="CA", avg_gpa=3.7,
        size="medium", majors=["Computer Science", "Engineering"], culture=NEUTRAL,
    )
    return University(**{**base, **over})


class TestWeights:
    def test_six_dimensions_summing_to_one(self):
        assert set(DEFAULT_WEIGHTS) == {
            "academic", "cost", "fit", "culture", "activities", "personality",
        }
        assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)


class TestActivityFit:
    def test_matching_activity_beats_unrelated_one(self):
        robotics = [Activity(name="FIRST Robotics Competition", kind="competition")]
        choir = [Activity(name="chamber choir", kind="club")]

        assert activity_fit(robotics, _uni()) > activity_fit(choir, _uni())

    def test_no_activities_is_neutral(self):
        """Saying nothing must not penalise a school."""
        assert activity_fit([], _uni()) == 0.5

    def test_recognises_a_competition_by_keyword(self):
        hackathon = [Activity(name="won a hackathon", kind="competition")]

        assert activity_fit(hackathon, _uni()) > 0.5

    def test_matches_against_the_school_not_a_fixed_list(self):
        """The same activity should help at an engineering school and not at an
        arts school - the signal is the pairing, not the activity alone."""
        robotics = [Activity(name="robotics club", kind="club")]
        arts = _uni(majors=["Studio Art", "Music"])

        assert activity_fit(robotics, _uni()) > activity_fit(robotics, arts)

    def test_stays_in_unit_interval(self):
        many = [Activity(name=n, kind="club") for n in ("robotics", "debate", "code", "music")]

        assert 0.0 <= activity_fit(many, _uni()) <= 1.0


class TestPersonalityFit:
    def test_intensity_prefers_a_more_selective_school(self):
        driven = Personality(intensity=1.0, scale=0.5)
        selective = _uni(acceptance_rate=0.05)
        open_access = _uni(acceptance_rate=0.9)

        assert personality_fit(driven, selective) > personality_fit(driven, open_access)

    def test_low_intensity_prefers_a_less_pressured_school(self):
        relaxed = Personality(intensity=0.0, scale=0.5)
        selective = _uni(acceptance_rate=0.05)
        open_access = _uni(acceptance_rate=0.9)

        assert personality_fit(relaxed, open_access) > personality_fit(relaxed, selective)

    def test_scale_prefers_a_bigger_campus(self):
        big = Personality(intensity=0.5, scale=1.0)

        assert personality_fit(big, _uni(enrollment=40000)) > personality_fit(
            big, _uni(enrollment=1200)
        )

    def test_neutral_answers_are_neutral(self):
        assert personality_fit(Personality(), _uni(acceptance_rate=0.3, enrollment=9000)) == 0.5

    def test_missing_school_data_does_not_crash_or_invent(self):
        """Most non-US schools have no acceptance rate; that axis is skipped."""
        driven = Personality(intensity=1.0, scale=0.5)

        assert 0.0 <= personality_fit(driven, _uni(acceptance_rate=None, enrollment=None)) <= 1.0


class TestProfileShape:
    def test_activities_and_personality_are_optional(self):
        profile = Profile(gpa=3.8, intended_major="Computer Science")

        assert profile.activities == []
        assert profile.personality.intensity == 0.5

    def test_activity_kind_is_constrained(self):
        with pytest.raises(ValidationError):
            Activity(name="x", kind="not-a-kind")
