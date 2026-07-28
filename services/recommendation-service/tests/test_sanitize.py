from app.llm import Review
from app.loop import sanitize_review


def test_drops_unknown_ids():
    clean = sanitize_review(Review(keep_ids=["u1", "ghost", "u2"]), ["u1", "u2"], 5)
    assert clean["keep_ids"] == ["u1", "u2"]


def test_dedupes_preserving_order():
    clean = sanitize_review(Review(keep_ids=["u2", "u1", "u2"]), ["u1", "u2"], 5)
    assert clean["keep_ids"] == ["u2", "u1"]


def test_truncates_to_top_k():
    clean = sanitize_review(Review(keep_ids=["u1", "u2", "u3"]), ["u1", "u2", "u3"], 2)
    assert clean["keep_ids"] == ["u1", "u2"]


def test_clamps_weight_feedback():
    clean = sanitize_review(
        Review(keep_ids=[], weight_feedback={"academic": 9.0, "cost": 0.01, "fit": 1.2}),
        ["u1"], 5,
    )
    assert clean["weight_feedback"] == {"academic": 1.5, "cost": 0.5, "fit": 1.2}


def test_coerces_confidence_range_and_type():
    assert sanitize_review(Review(keep_ids=[], confidence=5.0), ["u1"], 5)["confidence"] == 1.0
    assert sanitize_review(Review(keep_ids=[], confidence=-2), ["u1"], 5)["confidence"] == 0.0
    assert sanitize_review(Review(keep_ids=[], confidence="bad"), ["u1"], 5)["confidence"] == 0.0


def test_notes_filtered_to_allowed_ids():
    clean = sanitize_review(
        Review(keep_ids=[], notes={"u1": "ok", "ghost": "drop"}), ["u1"], 5
    )
    assert clean["notes"] == {"u1": "ok"}
