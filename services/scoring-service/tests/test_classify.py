"""Classification is exposed from the service that owns the pattern table, so
the UI cannot be shown one answer while the scorer uses another."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.scoring import classify_activity

client = TestClient(app)


def _post(**body):
    return client.post("/classify", json=body)


class TestClassifyFunction:
    def test_recognises_a_known_activity(self):
        assert "Computer Science" in classify_activity("FIRST Robotics", "competition")

    def test_returns_empty_for_something_unrecognised(self):
        """An empty list is the signal the UI uses to prompt for an explanation."""
        assert classify_activity("qqzzxx", "other") == []

    def test_matching_is_case_insensitive(self):
        assert classify_activity("ROBOTICS", "club") != []

    def test_the_description_rescues_an_unrecognised_name(self):
        """The description string was corrected from the original task brief
        draft ("built an autonomous rover and wrote the vision pipeline"),
        which matched no pattern in `_ACTIVITY_SUBJECTS` and so asserted
        behaviour the table does not have. `_ACTIVITY_SUBJECTS` was left
        untouched, as it must be: it also drives real scoring via
        `activity_fit`, and widening it to fit an invented example would
        change matching for every student to accommodate a test string that
        was never checked against the table. Only the test was fixed."""
        assert classify_activity("Science Bowl", "competition") == []
        assert "Computer Science" in classify_activity(
            "Science Bowl",
            "competition",
            "I wrote the code for our robot's autonomous vision system",
        )

    def test_is_deterministic(self):
        first = classify_activity("Model UN", "club")
        assert first == classify_activity("Model UN", "club")

    def test_agrees_with_what_the_scorer_matches(self):
        """The property that makes one implementation worth the extra hop: a
        school strong in a returned subject must score above neutral."""
        from app.schemas import Activity, Culture, University
        from app.scoring import activity_fit

        subjects = classify_activity("FIRST Robotics", "competition")
        assert subjects
        uni = University(
            id="u1", name="U", country="USA", location="CA",
            region="West", setting="urban", type="Private",
            avg_gpa=3.7, size="medium", majors=list(subjects),
            culture=Culture(collab=0.5, quirky=0.5, idealist=0.5,
                            research=0.5, spirit=0.5, seminar=0.5),
        )

        assert activity_fit([Activity(name="FIRST Robotics", kind="competition")], uni) > 0.5


class TestClassifyEndpoint:
    def test_returns_the_subjects(self):
        response = _post(name="FIRST Robotics", kind="competition")

        assert response.status_code == 200
        assert "Computer Science" in response.json()["subjects"]

    def test_passes_the_description_through(self):
        response = _post(
            name="Science Bowl",
            kind="competition",
            description="I wrote the code for our robot's autonomous vision system",
        )

        assert response.json()["subjects"] != []

    def test_name_is_required(self):
        assert client.post("/classify", json={"kind": "club"}).status_code == 422

    def test_rejects_an_unknown_kind(self):
        assert _post(name="x", kind="not-a-kind").status_code == 422
