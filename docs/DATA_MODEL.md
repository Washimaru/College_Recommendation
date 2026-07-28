# Data Model

Contracts in `docs/contracts/*.json` are the wire source of truth. This file
describes the domain entities behind them.

## StudentProfile (`profile.schema.json`)

- `gpa` — 0.0–4.0.
- `sat` — optional, 400–1600.
- `mbti` — four letters, `^[EI][NS][TF][JP]$`.
- `intended_major` — free text.
- `preferences` — `max_tuition`, `preferred_size` (small/medium/large),
  `locations[]`.
- `weights` — optional per-request overrides of the rubric weights.

## University (`score.schema.json` → `$defs.University`)

`id`, `name`, `avg_gpa`, `avg_sat`, `acceptance_rate` (0–1), `tuition`, `size`,
`location`, `majors[]`. Persisted in the `universities` table (`db/schema.sql`).

## Scoring (`score.schema.json`)

`RankRequest {profile, weight_feedback, universities[]}` →
`RankResponse {scores[]}` where each `ScoredUniversity` has `university_id`,
`score` (0–1), and per-component breakdown. Sorted by descending score, then
ascending `university_id`.

## Recommendation (`recommendation.schema.json`)

`RecommendationRequest {profile, max_iterations, top_k}` →
`RecommendationResponse {results[], confidence, stop_reason, trace[]}`.
`stop_reason ∈ {R1_converged, R2_confident, R3_no_change, R4_iteration_cap}`.
Persisted in the `recommendations` table.

## Mirrors (must move together)

`docs/contracts/*.json` ↔ `services/scoring-service/app/schemas.py` ↔
`services/recommendation-service/app/schemas.py` ↔ `services/gateway/src/types.ts`.
Changing one shape without the others (and a version bump) is contract drift (H3).
