
from app.llm import MockLLM
from app.loop import _stop_reason, iter_loop, run_loop

from .conftest import FlipLLM, StaticLLM, scored


def const_rank(scored_list):
    return lambda weight_feedback: list(scored_list)


def test_R1_converged(profile, universities):
    ranked = scored([("u1", 0.9), ("u2", 0.8), ("u3", 0.7)])
    resp = iter_loop(const_rank(ranked), MockLLM(top_k=2), profile, universities,
                     max_iterations=5, top_k=2)
    # MockLLM keeps exactly the top-k, which equals the ranking's top set -> R1.
    assert resp.stop_reason == "R1_converged"
    assert resp.trace[0].stop_reason == "R1_converged"
    assert [r.university_id for r in resp.results] == ["u1", "u2"]


def test_R2_confident(profile, universities):
    ranked = scored([("u1", 0.9), ("u2", 0.8), ("u3", 0.7)])
    # keep_ids differ from top set so R1 cannot fire; confidence high -> R2.
    llm = StaticLLM(keep_ids=["u3"], confidence=0.95)
    resp = iter_loop(const_rank(ranked), llm, profile, universities, max_iterations=5, top_k=2)
    assert resp.stop_reason == "R2_confident"


def test_R3_no_change(profile, universities):
    ranked = scored([("u1", 0.9), ("u2", 0.8), ("u3", 0.7)])
    # Empty keep + low confidence + unchanging ranking -> R3 on the 2nd iteration.
    llm = StaticLLM(keep_ids=[], confidence=0.2)
    resp = iter_loop(const_rank(ranked), llm, profile, universities, max_iterations=5, top_k=2)
    assert resp.stop_reason == "R3_no_change"
    assert resp.trace[0].stop_reason is None
    assert resp.trace[1].stop_reason == "R3_no_change"


def test_R4_iteration_cap(profile, universities):
    # A rank_fn whose order depends on weight_feedback, plus an LLM that flips the
    # weights every turn: the ranking never stabilizes, so only the hard cap stops it.
    def rank_fn(weight_feedback):
        factor = weight_feedback.get("academic", 1.0)
        base = scored([("u1", 0.9), ("u2", 0.8)])
        if factor < 1.0:  # flip the order
            base = list(reversed(base))
        return base

    resp = iter_loop(rank_fn, FlipLLM(), profile, universities, max_iterations=4, top_k=2)
    assert resp.stop_reason == "R4_iteration_cap"
    assert len(resp.trace) == 4
    assert resp.trace[-1].iteration == 3


def test_precedence_R1_beats_R2(profile, universities):
    ranked = scored([("u1", 0.9), ("u2", 0.8)])
    # Both R1 (keep==top) and R2 (high confidence) are satisfiable; R1 must win.
    llm = StaticLLM(keep_ids=["u1", "u2"], confidence=0.99)
    resp = iter_loop(const_rank(ranked), llm, profile, universities, max_iterations=5, top_k=2)
    assert resp.stop_reason == "R1_converged"


def test_stop_reason_returns_none_when_nothing_fires():
    assert _stop_reason(0, 5, ["u1"], None, [], 0.1) is None


def test_run_loop_emits_iteration_then_final(profile, universities):
    ranked = scored([("u1", 0.9), ("u2", 0.8)])
    events = list(run_loop(const_rank(ranked), MockLLM(top_k=2), profile, universities,
                           max_iterations=5, top_k=2))
    assert events[-1]["type"] == "final"
    assert all(e["type"] == "iteration" for e in events[:-1])


def test_results_fall_back_to_top_k_when_keep_empty(profile, universities):
    ranked = scored([("u1", 0.9), ("u2", 0.8), ("u3", 0.7)])
    llm = StaticLLM(keep_ids=[], confidence=0.2)
    resp = iter_loop(const_rank(ranked), llm, profile, universities, max_iterations=2, top_k=2)
    assert [r.university_id for r in resp.results] == ["u1", "u2"]
