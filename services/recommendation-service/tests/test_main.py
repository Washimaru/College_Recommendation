from fastapi.testclient import TestClient

import app.main as main
from app.schemas import ScoredUniversity


def _fake_rank_fn_factory(profile, universities, *a, **k):
    ranked = sorted(universities, key=lambda u: (-u.avg_gpa, u.id))

    def rank_fn(weight_feedback):
        return [
            ScoredUniversity(university_id=u.id, score=round(u.avg_gpa / 4.0, 6),
                             components={"academic": round(u.avg_gpa / 4.0, 6)})
            for u in ranked
        ]

    return rank_fn


client = TestClient(main.app)


def test_healthz():
    assert client.get("/healthz").json() == {"status": "ok"}


def test_recommend(monkeypatch):
    monkeypatch.setattr(main, "make_rank_fn", _fake_rank_fn_factory)
    payload = {"profile": {"gpa": 3.8, "sat": 1400,
                           "intended_major": "Computer Science"}, "top_k": 3}
    r = client.post("/recommend", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["stop_reason"].startswith("R")
    assert 0.0 <= body["confidence"] <= 1.0
    assert len(body["results"]) == 3


def test_recommend_stream(monkeypatch):
    monkeypatch.setattr(main, "make_rank_fn", _fake_rank_fn_factory)
    payload = {"profile": {"gpa": 3.8,
                           "intended_major": "Computer Science"}, "top_k": 2}
    r = client.post("/recommend/stream", json=payload)
    assert r.status_code == 200
    assert "event: final" in r.text
    assert "event: iteration" in r.text


def test_rejects_mbti_as_unknown_field():
    """Removed in contract v2.0.0; a stale client must fail loudly."""
    payload = {"profile": {"gpa": 3.8, "mbti": "INTJ", "intended_major": "CS"}}
    assert client.post("/recommend", json=payload).status_code == 422
