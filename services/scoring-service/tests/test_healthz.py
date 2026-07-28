from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_rank_endpoint(profile, universities):
    payload = {
        "profile": profile.model_dump(),
        "universities": [u.model_dump() for u in universities],
    }
    r = client.post("/rank", json=payload)
    assert r.status_code == 200
    assert len(r.json()["scores"]) == 3


def test_rank_rejects_mbti_as_unknown_field(universities):
    """MBTI was removed in contract v2.0.0. The endpoint must reject it rather
    than silently ignore it, so a stale client fails loudly."""
    payload = {
        "profile": {"gpa": 3.5, "mbti": "INTJ", "intended_major": "Math"},
        "universities": [u.model_dump() for u in universities],
    }
    r = client.post("/rank", json=payload)
    assert r.status_code == 422


def test_rank_rejects_out_of_range_culture_pref(universities):
    """Replacement validation for the dimension MBTI used to occupy."""
    payload = {
        "profile": {
            "gpa": 3.5,
            "intended_major": "Math",
            "culture_prefs": {"collab": 1.7},
        },
        "universities": [u.model_dump() for u in universities],
    }
    r = client.post("/rank", json=payload)
    assert r.status_code == 422
