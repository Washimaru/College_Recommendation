from app.schemas import Profile, RankRequest
from app.scoring import DEFAULT_WEIGHTS, rank, score_one


def _req(profile, universities, weight_feedback=None):
    return RankRequest(profile=profile, universities=universities,
                       weight_feedback=weight_feedback or {})


def test_scores_in_unit_interval(profile, universities):
    resp = rank(_req(profile, universities))
    assert resp.scores
    for s in resp.scores:
        assert 0.0 <= s.score <= 1.0
        assert set(s.components) == set(DEFAULT_WEIGHTS)


def test_sorted_desc_score_then_id(profile, universities):
    resp = rank(_req(profile, universities))
    keys = [(-s.score, s.university_id) for s in resp.scores]
    assert keys == sorted(keys)


def test_determinism_same_input_same_output(profile, universities):
    a = rank(_req(profile, universities)).model_dump()
    b = rank(_req(profile, universities)).model_dump()
    assert a == b


def test_major_match_beats_non_match(profile, universities):
    resp = rank(_req(profile, universities))
    top = resp.scores[0].university_id
    # u2 does not have the major the student wants; fit scores it lower.
    assert top in {"u1", "u3"}
    ranking = [s.university_id for s in resp.scores]
    assert ranking.index("u2") == len(ranking) - 1


def test_empty_universities_yields_empty_scores(profile):
    resp = rank(_req(profile, []))
    assert resp.scores == []


def test_weight_feedback_shifts_score(profile, universities):
    base = {s.university_id: s.score for s in rank(_req(profile, universities)).scores}
    boosted = {s.university_id: s.score
               for s in rank(_req(profile, universities, {"cost": 1.5})).scores}
    assert base != boosted


def test_cost_fit_without_cap(universities):
    p = Profile(gpa=3.5, sat=1200, intended_major="Math")
    resp = rank(_req(p, universities))
    assert all(0.0 <= s.components["cost"] <= 1.0 for s in resp.scores)


def test_no_sat_falls_back_to_gpa(universities):
    p = Profile(gpa=3.9, intended_major="Math")
    uni = universities[0]
    s = score_one(p, uni, DEFAULT_WEIGHTS)
    assert 0.0 <= s.components["academic"] <= 1.0
