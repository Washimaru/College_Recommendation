"""Runtime recommendation loop.

Flow (per docs/LOOP_ENGINEERING.md):
    run_loop: rank_fn -> llm.review -> sanitize_review -> _stop_reason

Two invariants that live in CODE, never in a prompt:
  * sanitize_review is the trust boundary for the LLM output.
  * _stop_reason evaluates R1 > R2 > R3 > R4 in that fixed order; R4 is the
    unconditional hard cap at i == max_iterations - 1.

`run_loop` is the single source of truth; it yields one event per iteration and
a terminal "final" event. `iter_loop` (blocking) and the SSE endpoint both
consume it, so streaming and non-streaming can never diverge.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator

from .llm import LLM, Review
from .schemas import (
    RecommendationResponse,
    Result,
    ScoredUniversity,
    TraceStep,
    University,
    UniversitySummary,
)

# rank_fn takes clamped weight_feedback and returns candidates sorted by the
# scoring service (descending score, ascending id).
RankFn = Callable[[dict[str, float]], list[ScoredUniversity]]

CONFIDENCE_THRESHOLD = 0.9
WEIGHT_FEEDBACK_MIN = 0.5
WEIGHT_FEEDBACK_MAX = 1.5

# Reach/target/safety boundary, in GPA points either side of a match.
# Inherited from the original UniMatch project's admitTier.
ADMIT_TIER_DELTA = 0.12

# Selectivity threshold for the extreme_reach tier. A stated judgement, not a
# measured finding - like ADMIT_TIER_DELTA, the copy must present it that way.
EXTREME_REACH_ACCEPTANCE_RATE_MAX = 0.15


def admit_tier(
    student_gpa: float | None, school_avg_gpa: float, acceptance_rate: float | None
) -> str | None:
    """Classify a school relative to the student. None when the student gave no
    GPA - there is nothing to compare, and a guess would be worse than a gap.

    extreme_reach is checked first and is keyed on selectivity, not GPA: at a
    4% admit rate a 4.0 student is still rejected far more often than not, so
    a GPA that clears the school's average must not read as a "target". A null
    acceptance_rate (every non-US school, and some US ones) never fires this
    tier - it falls through to the GPA rule exactly as if the check were
    absent, so a missing value cannot manufacture a tier.
    """
    if student_gpa is None:
        return None
    if acceptance_rate is not None and acceptance_rate <= EXTREME_REACH_ACCEPTANCE_RATE_MAX:
        return "extreme_reach"
    delta = school_avg_gpa - student_gpa
    if delta >= ADMIT_TIER_DELTA:
        return "reach"
    if delta <= -ADMIT_TIER_DELTA:
        return "safety"
    return "target"


def sanitize_review(raw: Review, candidate_ids: list[str], top_k: int) -> Review:
    """Trust boundary for LLM output. Drops unknown ids, dedupes preserving
    order, clamps weight_feedback to [0.5, 1.5], coerces confidence to [0, 1]."""
    allowed = set(candidate_ids)
    seen: set[str] = set()
    keep: list[str] = []
    for uid in raw.get("keep_ids", []):
        if uid in allowed and uid not in seen:
            keep.append(uid)
            seen.add(uid)
    keep = keep[:top_k]

    raw_feedback = raw.get("weight_feedback", {}) or {}
    weight_feedback = {
        str(k): max(WEIGHT_FEEDBACK_MIN, min(WEIGHT_FEEDBACK_MAX, float(v)))
        for k, v in raw_feedback.items()
    }

    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    notes = {k: str(v) for k, v in (raw.get("notes", {}) or {}).items() if k in allowed}

    return Review(keep_ids=keep, confidence=confidence,
                  weight_feedback=weight_feedback, notes=notes)


def _stop_reason(
    iteration: int,
    max_iterations: int,
    top_ids: list[str],
    prev_top_ids: list[str] | None,
    kept_ids: list[str],
    confidence: float,
) -> str | None:
    """R1 > R2 > R3 > R4, evaluated in this fixed order. First match wins."""
    if kept_ids and kept_ids == top_ids:  # R1: LLM selection == current ranking
        return "R1_converged"
    if confidence >= CONFIDENCE_THRESHOLD:  # R2: confident enough to stop
        return "R2_confident"
    if prev_top_ids is not None and top_ids == prev_top_ids:  # R3: ranking stable
        return "R3_no_change"
    if iteration == max_iterations - 1:  # R4: hard cap, unconditional
        return "R4_iteration_cap"
    return None


def _summarize(uni: University) -> UniversitySummary:
    return UniversitySummary(
        country=uni.country,
        location=uni.location,
        state=uni.state,
        region=uni.region,
        setting=uni.setting,
        type=uni.type,
        avg_gpa=uni.avg_gpa,
        avg_sat=uni.avg_sat,
        acceptance_rate=uni.acceptance_rate,
        net_price=uni.net_price,
        sticker_tuition=uni.sticker_tuition,
        tuition_in_state=uni.tuition_in_state,
        programs=uni.programs,
        enrollment=uni.enrollment,
        size=uni.size,
        majors=uni.majors,
        culture=uni.culture,
        population=uni.population,
        url=uni.url,
        net_price_calculator_url=uni.net_price_calculator_url,
        details=uni.details,
        provenance=uni.provenance,
    )


def _build_results(
    scored: list[ScoredUniversity],
    clean: Review,
    universities: dict[str, University],
    profile,
    top_k: int,
) -> list[Result]:
    by_id = {s.university_id: s for s in scored}
    notes = clean["notes"]
    chosen = clean["keep_ids"] or [s.university_id for s in scored[:top_k]]
    student_gpa = getattr(profile, "gpa", None)
    results = []
    for uid in chosen:
        if uid not in by_id or uid not in universities:
            continue
        uni = universities[uid]
        results.append(
            Result(
                university_id=uid,
                name=uni.name,
                score=by_id[uid].score,
                rationale=notes.get(uid, "Top-ranked match for this profile."),
                admit_tier=admit_tier(student_gpa, uni.avg_gpa, uni.acceptance_rate),
                university=_summarize(uni),
            )
        )
    return results


def run_loop(
    rank_fn: RankFn,
    llm: LLM,
    profile,
    universities: dict[str, University],
    max_iterations: int = 5,
    top_k: int = 5,
) -> Iterator[dict]:
    """Yield {'type': 'iteration', 'step': TraceStep} events, then a single
    {'type': 'final', 'response': RecommendationResponse} event."""
    weight_feedback: dict[str, float] = {}
    prev_top_ids: list[str] | None = None
    trace: list[TraceStep] = []
    stop_reason: str | None = None
    scored: list[ScoredUniversity] = []
    clean: Review = Review(keep_ids=[], confidence=0.0, weight_feedback={}, notes={})

    for i in range(max_iterations):
        scored = rank_fn(weight_feedback)
        candidate_ids = [s.university_id for s in scored]
        top_ids = candidate_ids[:top_k]

        raw = llm.review(profile, scored, i)
        clean = sanitize_review(raw, candidate_ids, top_k)

        stop_reason = _stop_reason(
            iteration=i,
            max_iterations=max_iterations,
            top_ids=top_ids,
            prev_top_ids=prev_top_ids,
            kept_ids=clean["keep_ids"],
            confidence=clean["confidence"],
        )
        step = TraceStep(iteration=i, top_ids=top_ids,
                         confidence=clean["confidence"], stop_reason=stop_reason)
        trace.append(step)
        yield {"type": "iteration", "step": step}

        if clean["weight_feedback"]:
            weight_feedback = clean["weight_feedback"]
        prev_top_ids = top_ids
        if stop_reason is not None:
            break

    assert stop_reason is not None  # R4 guarantees termination
    response = RecommendationResponse(
        results=_build_results(scored, clean, universities, profile, top_k),
        confidence=clean["confidence"],
        stop_reason=stop_reason,
        trace=trace,
    )
    yield {"type": "final", "response": response}


def iter_loop(
    rank_fn: RankFn,
    llm: LLM,
    profile,
    universities: dict[str, University],
    max_iterations: int = 5,
    top_k: int = 5,
) -> RecommendationResponse:
    """Blocking driver: run the loop to completion and return the final response."""
    final: RecommendationResponse | None = None
    for event in run_loop(rank_fn, llm, profile, universities, max_iterations, top_k):
        if event["type"] == "final":
            final = event["response"]
    assert final is not None
    return final
