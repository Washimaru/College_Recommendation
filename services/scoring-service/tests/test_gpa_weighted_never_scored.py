"""gpa_weighted is display-only and must never enter the rubric.

Per docs/superpowers/specs/2026-08-03-gpa-scales-tiers-and-profiles-design.md:
the weighted/unweighted gap is a real course-rigor signal, but we have no
evidence for what weight it deserves, and inventing one would move every
ranking on a number we made up. So two profiles identical except for
gpa_weighted must produce byte-identical RankResponse output - not as a
seventh dimension, and not folded into `academic` as a modifier.
"""
from __future__ import annotations

from app.schemas import Profile, RankRequest
from app.scoring import rank


def test_gpa_weighted_never_changes_the_rank_response(universities):
    base = Profile(gpa=3.8, sat=1400, intended_major="Computer Science")
    with_weighted = Profile(
        gpa=3.8, sat=1400, intended_major="Computer Science", gpa_weighted=4.6
    )

    base_resp = rank(RankRequest(profile=base, universities=universities))
    weighted_resp = rank(RankRequest(profile=with_weighted, universities=universities))

    assert base_resp.model_dump() == weighted_resp.model_dump()


def test_gpa_weighted_never_changes_the_rank_response_across_the_range(universities):
    """Same pin, swept across the field's full 0.0-5.0 range, so a modifier
    that only kicks in at some values (e.g. only above 4.0) can't hide."""
    for value in (0.0, 2.5, 4.0, 4.42, 5.0):
        base = Profile(gpa=3.5, sat=1300, intended_major="Math")
        with_weighted = Profile(
            gpa=3.5, sat=1300, intended_major="Math", gpa_weighted=value
        )
        base_resp = rank(RankRequest(profile=base, universities=universities))
        weighted_resp = rank(RankRequest(profile=with_weighted, universities=universities))
        assert base_resp.model_dump() == weighted_resp.model_dump()
