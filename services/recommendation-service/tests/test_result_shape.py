"""Result carries what the UI must render.

A ranked list alone cannot show Reach/Target/Safety (needs the school's
avg_gpa) or distinguish an estimate from a federal statistic (needs
provenance). Contract recommendation.schema.json v2.0.0 adds both.
"""
from __future__ import annotations

from app.loop import iter_loop
from app.schemas import Culture, University

from .conftest import StaticLLM, scored

NEUTRAL = Culture(collab=0.5, quirky=0.5, idealist=0.5, research=0.5, spirit=0.5, seminar=0.5)


def _universities() -> dict[str, University]:
    return {
        "u1": University(
            id="u1", name="Alpha", country="USA", location="CA", avg_gpa=3.95,
            avg_sat=1550, acceptance_rate=0.05, net_price=20000, enrollment=4600,
            size="small", majors=["Computer Science"], culture=NEUTRAL,
            provenance={"avg_sat": "observed", "acceptance_rate": "observed"},
        ),
        "u2": University(
            id="u2", name="Beta", country="UK", location="Oxford", avg_gpa=3.4,
            avg_sat=None, acceptance_rate=None, net_price=9000,
            size="medium", majors=["PPE"], culture=NEUTRAL,
            provenance={"avg_sat": "not_applicable", "acceptance_rate": "absent"},
        ),
    }


def _run(profile, universities):
    return iter_loop(
        lambda _: scored([("u1", 0.9), ("u2", 0.8)]),
        StaticLLM(keep_ids=["u1", "u2"], confidence=0.95),
        profile,
        universities,
        max_iterations=1,
        top_k=2,
    )


def test_result_includes_admit_tier(profile):
    """profile fixture is gpa 3.8: u1 at 3.95 is a reach, u2 at 3.4 a safety."""
    response = _run(profile, _universities())

    tiers = {r.university_id: r.admit_tier for r in response.results}
    assert tiers == {"u1": "reach", "u2": "safety"}


def test_result_includes_university_summary(profile):
    response = _run(profile, _universities())
    alpha = next(r for r in response.results if r.university_id == "u1")

    assert alpha.university.avg_gpa == 3.95
    assert alpha.university.acceptance_rate == 0.05
    assert alpha.university.net_price == 20000
    assert alpha.university.country == "USA"


def test_summary_preserves_nulls_and_provenance(profile):
    """The UI needs to tell 'not applicable' from 'absent' from a real zero."""
    response = _run(profile, _universities())
    beta = next(r for r in response.results if r.university_id == "u2")

    assert beta.university.avg_sat is None
    assert beta.university.acceptance_rate is None
    assert beta.university.provenance["avg_sat"] == "not_applicable"
    assert beta.university.provenance["acceptance_rate"] == "absent"


def test_summary_carries_majors_and_culture_for_the_detail_view(profile):
    """The detail modal shows what a school offers and how it feels; both come
    from tier 1 and are present for every school in the catalog."""
    response = _run(profile, _universities())
    alpha = next(r for r in response.results if r.university_id == "u1")

    assert alpha.university.majors == ["Computer Science"]
    assert alpha.university.culture.research == 0.5
