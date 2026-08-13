"""Out-of-state applicants pay more than net_price says.

`net_price` is IPEDS/Scorecard's average net price, and at a public
institution that measure is computed for students paying **in-state** tuition.
So a Michigan resident and a Texan looking at Michigan were shown the same
$13,138, when the Texan pays roughly the tuition gap ($60,946 - $17,736) on
top of it. Cost is 18% of the score, so this was not only a display problem:
every out-of-state public school scored as if it were priced for a local.

The correction is a **stated adjustment**, in the same spirit as the
admit-tier thresholds: it is applied to the score, never written into the
catalog and never shown as an observed figure. It only fires when the student
volunteers a home state — a student who does not answer sees exactly what they
saw before.
"""
from __future__ import annotations

from app.schemas import Culture, Profile, University
from app.scoring import _cost_fit

NEUTRAL = Culture(collab=0.5, quirky=0.5, idealist=0.5, research=0.5, spirit=0.5, seminar=0.5)


def _uni(**overrides) -> University:
    base = dict(
        id="um", name="Michigan", country="USA", location="Ann Arbor, MI",
        state="MI", region="Midwest", setting="suburban", type="Public",
        avg_gpa=3.8, size="large", majors=["Engineering"], culture=NEUTRAL,
        net_price=13138, tuition_in_state=17736, sticker_tuition=60946,
    )
    return University(**{**base, **overrides})


def _profile(**preferences) -> Profile:
    return Profile(gpa=3.8, intended_major="Engineering", preferences=preferences)


class TestNoHomeStateChangesNothing:
    def test_an_unanswered_home_state_scores_exactly_as_before(self):
        """The whole feature is opt-in; silence must cost nothing."""
        assert _cost_fit(_profile(max_tuition=20000), _uni()) == 1.0

    def test_the_no_cap_branch_is_untouched_too(self):
        without = _cost_fit(_profile(), _uni())
        with_home = _cost_fit(_profile(home_state="MI"), _uni())

        assert without == with_home


class TestResident:
    def test_a_resident_pays_the_published_net_price(self):
        assert _cost_fit(_profile(max_tuition=20000, home_state="MI"), _uni()) == 1.0

    def test_case_does_not_decide_residency(self):
        assert _cost_fit(_profile(max_tuition=20000, home_state="mi"), _uni()) == 1.0


class TestNonResident:
    def test_the_out_of_state_premium_is_added(self):
        """13,138 + (60,946 - 17,736) = 56,348, well over a $20k cap."""
        score = _cost_fit(_profile(max_tuition=20000, home_state="TX"), _uni())

        assert score < 1.0
        assert score == round(max(0.0, 1.0 - (56348 - 20000) / 20000), 6)

    def test_a_resident_scores_better_than_a_non_resident_at_the_same_school(self):
        resident = _cost_fit(_profile(max_tuition=30000, home_state="MI"), _uni())
        visitor = _cost_fit(_profile(max_tuition=30000, home_state="TX"), _uni())

        assert resident > visitor

    def test_a_private_school_is_unaffected_since_everyone_pays_alike(self):
        private = _uni(
            type="Private", state="MA", net_price=20111,
            tuition_in_state=62396, sticker_tuition=62396,
        )

        assert _cost_fit(_profile(max_tuition=25000, home_state="TX"), private) == _cost_fit(
            _profile(max_tuition=25000, home_state="MA"), private
        )

    def test_a_school_missing_either_figure_is_not_adjusted_on_a_guess(self):
        no_in_state = _uni(tuition_in_state=None)

        assert _cost_fit(_profile(max_tuition=20000, home_state="TX"), no_in_state) == 1.0

    def test_an_unknown_net_price_stays_neutral(self):
        assert _cost_fit(_profile(max_tuition=20000, home_state="TX"), _uni(net_price=None)) == 0.5

    def test_a_non_us_school_has_no_residency_to_be_wrong_about(self):
        abroad = _uni(
            country="UK", state=None, type="Public", location="Oxford",
            region="International", net_price=30000,
            tuition_in_state=None, sticker_tuition=None,
        )

        assert _cost_fit(_profile(max_tuition=35000, home_state="TX"), abroad) == 1.0

    def test_the_premium_also_applies_without_a_stated_cap(self):
        resident = _cost_fit(_profile(home_state="MI"), _uni())
        visitor = _cost_fit(_profile(home_state="TX"), _uni())

        assert visitor < resident
