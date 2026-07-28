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


def test_rank_rejects_invalid_mbti(universities):
    payload = {
        "profile": {"gpa": 3.5, "mbti": "XXXX", "intended_major": "Math"},
        "universities": [u.model_dump() for u in universities],
    }
    r = client.post("/rank", json=payload)
    assert r.status_code == 422
