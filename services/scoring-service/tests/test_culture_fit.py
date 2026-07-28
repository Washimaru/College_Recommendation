"""Preference-weighted agreement, the replacement for the MBTI personality
dimension removed in contract v2.0.0.

    importance_k = |pref_k - 0.5| * 2
    agreement_k  = 1 - |pref_k - culture_k|
    culture_fit  = sum(importance * agreement) / sum(importance)

Cosine was rejected for this: the axes are bipolar, so a low-low match is a
real match, and cosine scores it zero. These tests pin that down.
"""
from __future__ import annotations

from app.schemas import Culture, CulturePrefs
from app.scoring import culture_fit


def _culture(**overrides) -> Culture:
    base = dict.fromkeys(
        ("collab", "quirky", "idealist", "research", "spirit", "seminar"), 0.5
    )
    return Culture(**{**base, **overrides})


def test_low_to_low_agreement_scores_perfect():
    """A student wanting a competitive campus, matched to a competitive campus.
    Cosine gives 0 * 0 = 0 here; this is the bug that rejected it."""
    prefs = CulturePrefs(collab=0.0)
    uni = _culture(collab=0.0)

    assert culture_fit(prefs, uni) == 1.0


def test_high_to_high_agreement_scores_perfect():
    prefs = CulturePrefs(collab=1.0)
    uni = _culture(collab=1.0)

    assert culture_fit(prefs, uni) == 1.0


def test_opposite_poles_score_zero():
    prefs = CulturePrefs(collab=1.0)
    uni = _culture(collab=0.0)

    assert culture_fit(prefs, uni) == 0.0


def test_all_sliders_centred_is_neutral():
    """No preference expressed: neutral 0.5, and no division by zero."""
    assert culture_fit(CulturePrefs(), _culture()) == 0.5
    assert culture_fit(CulturePrefs(), _culture(collab=1.0, spirit=0.0)) == 0.5


def test_untouched_axes_do_not_dilute_a_strong_preference():
    """Only axes the student moved should count. A mismatch on an axis they
    left centred must not drag the score down."""
    prefs = CulturePrefs(research=1.0)
    uni = _culture(research=1.0, spirit=0.0, quirky=0.0)

    assert culture_fit(prefs, uni) == 1.0


def test_stays_within_unit_interval_across_extremes():
    for pref_value in (0.0, 0.25, 0.5, 0.75, 1.0):
        for uni_value in (0.0, 0.25, 0.5, 0.75, 1.0):
            score = culture_fit(
                CulturePrefs(collab=pref_value, spirit=1 - pref_value),
                _culture(collab=uni_value, spirit=uni_value),
            )
            assert 0.0 <= score <= 1.0
