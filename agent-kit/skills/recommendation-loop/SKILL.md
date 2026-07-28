---
name: recommendation-loop
description: The runtime loop in recommendation-service — control flow, the sanitize_review trust boundary, and the R1>R2>R3>R4 stop-reason precedence.
---

# recommendation-loop

`services/recommendation-service/app/loop.py`. `run_loop` is the single source of
truth; per iteration: `rank_fn(weight_feedback)` → `llm.review` →
`sanitize_review` → `_stop_reason`. It yields one event per iteration and a
terminal `final` event; `iter_loop` (blocking) and `/recommend/stream` (SSE) both
consume it.

`sanitize_review` is the trust boundary: drops ids not in the candidate set,
dedupes preserving order, clamps `weight_feedback` to `[0.5,1.5]`, coerces
confidence to `[0,1]`. Never move these into a prompt.

`_stop_reason` precedence is **R1 > R2 > R3 > R4**, in fixed order:
R1 converged (LLM keep == current top set) · R2 confident (≥ 0.9) · R3 no change
(ranking equals previous) · R4 iteration cap at `i == max_iterations - 1` (the
unconditional hard stop). The LLM is behind the `LLM` protocol with a
deterministic `MockLLM`; unit tests stay offline.
