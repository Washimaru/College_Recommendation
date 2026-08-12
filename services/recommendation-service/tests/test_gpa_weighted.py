"""Profile.gpa_weighted mirror of scoring-service's contract test.

Weighted GPA (0.0-5.0), optional, displayed only - never scored, never
converted. See docs/superpowers/specs/
2026-08-03-gpa-scales-tiers-and-profiles-design.md decision 1, and
scoring-service/tests/test_contract_v2.py for the sibling assertions.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import CONTRACT_VERSION, Profile


def test_contract_version_is_6():
    assert CONTRACT_VERSION == "6.0.0"


def test_profile_gpa_weighted_is_optional():
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
