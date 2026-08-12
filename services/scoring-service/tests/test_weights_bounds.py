"""The weight override is public, so it has to be bounded.

`profile.weights` travels gateway -> recommendation-service -> scoring-service
untouched, and `_resolve_weights` normalises by the sum of the weights. Before
v6.0.0 each field was `ge=0` with no ceiling, so `{"weights": {"cost": 999999}}`
made cost ~100% of every score - the rest of the rubric silently stopped
mattering. A weight is a share of the rubric, so 1.0 is its ceiling.

`weight_feedback` is the same hazard one layer down: the loop clamps it to
[0.5, 1.5], but scoring-service is deployed on its own port and validated
nothing, so the clamp was only as good as the caller.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import Profile, RankRequest, Weights
from app.scoring import DEFAULT_WEIGHTS, _resolve_weights


def _profile(**overrides) -> Profile:
    return Profile(gpa=3.7, intended_major="Computer Science", **overrides)


class TestWeightBounds:
    def test_a_weight_may_be_the_whole_share(self):
        assert Weights(cost=1.0).cost == 1.0

    def test_a_weight_above_one_is_rejected(self):
        with pytest.raises(ValidationError):
            Weights(cost=1.0001)

    def test_the_absurd_override_is_rejected(self):
        with pytest.raises(ValidationError):
            Profile(gpa=3.7, intended_major="CS", weights={"cost": 999999})

    def test_a_negative_weight_is_still_rejected(self):
        with pytest.raises(ValidationError):
            Weights(cost=-0.1)

    def test_every_dimension_is_bounded_the_same_way(self):
        for dimension in DEFAULT_WEIGHTS:
            with pytest.raises(ValidationError, match=dimension):
                Weights(**{dimension: 2.0})


class TestOneDimensionCannotTakeOverTheScore:
    def test_the_largest_legal_override_leaves_the_rubric_intact(self):
        """Maxing one weight while leaving the others at their defaults gives
        that dimension 55% of the score - a strong preference, not the whole
        answer. 999999 used to give it 99.9999%."""
        weights = _resolve_weights(_profile(weights=Weights(cost=1.0)), {})

        share = weights["cost"] / sum(weights.values())

        assert round(share, 6) == 0.549451
        assert share < 0.56

    def test_the_other_five_dimensions_keep_their_defaults(self):
        weights = _resolve_weights(_profile(weights=Weights(cost=1.0)), {})

        assert {k: v for k, v in weights.items() if k != "cost"} == {
            k: v for k, v in DEFAULT_WEIGHTS.items() if k != "cost"
        }

    def test_feedback_cannot_push_a_maxed_weight_past_its_ceiling_by_much(self):
        """weight_feedback multiplies after the override, so its own clamp is
        what stops 1.0 becoming unbounded on the next iteration."""
        weights = _resolve_weights(_profile(weights=Weights(cost=1.0)), {"cost": 1.5})

        assert weights["cost"] == 1.5
        assert weights["cost"] / sum(weights.values()) < 0.65


class TestWeightFeedbackBounds:
    def test_the_clamped_range_is_accepted(self):
        request = RankRequest(profile=_profile(), weight_feedback={"cost": 1.5})

        assert request.weight_feedback == {"cost": 1.5}

    def test_an_unclamped_boost_is_rejected(self):
        with pytest.raises(ValidationError):
            RankRequest(profile=_profile(), weight_feedback={"cost": 999999})

    def test_a_value_below_the_floor_is_rejected(self):
        with pytest.raises(ValidationError):
            RankRequest(profile=_profile(), weight_feedback={"cost": 0.0})

    def test_no_feedback_is_still_the_default(self):
        assert RankRequest(profile=_profile()).weight_feedback == {}
