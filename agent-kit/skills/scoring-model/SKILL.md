---
name: scoring-model
description: The deterministic weighted rubric in scoring-service — component functions, default weights, MBTI→trait priors, and weight_feedback handling.
---

# scoring-model

`services/scoring-service/app/scoring.py`. Four components, each in `[0,1]`:
`academic` (student vs. university gpa/sat), `cost` (tuition vs. `max_tuition`),
`fit` (major + preferred size + location), `personality` (MBTI priors: E/I →
campus size, J/P → selectivity). Final score = weighted, weight-normalized sum,
clamped to `[0,1]`.

`DEFAULT_WEIGHTS = {academic .35, cost .20, fit .25, personality .20}`, overridable
by `profile.weights`, then multiplicatively by `weight_feedback` (already clamped
to `[0.5,1.5]` by the loop). Ranking is sorted by `-score` then `university_id`.

Determinism is law: no `random`, no clock, no LLM. Same `RankRequest` ⇒ same
`RankResponse` (guarded by a test).
