# Data Model

Contracts in `docs/contracts/*.json` are the wire source of truth, currently at
**v6.0.0**. This file describes the domain entities behind them.

The governing rule, everywhere below: **a missing value is `null`.** It is never
derived, inferred, estimated, or defaulted to zero. `provenance` records where
each figure came from, and the UI renders `n/a` (does not apply) distinctly from
an em dash (we don't have it) — never as `0`.

## StudentProfile (`profile.schema.json`)

- `gpa` — 0.0–4.0.
- `sat` — optional, 400–1600. Absent for test-optional applicants and never
  inferred from GPA.
- `intended_major` — free text.
- `culture_prefs` — six bipolar axes in [0,1] (`collab`, `quirky`, `idealist`,
  `research`, `spirit`, `seminar`). 0.5 means *no preference* and drops out of
  the average entirely rather than counting as neutral agreement.
- `personality` — `intensity` and `scale`, derived from the questionnaire, on
  axes the culture vector deliberately does not cover so nothing is scored twice.
- `activities[]` — `{name, kind, years?, description?}`. `description` is the
  student's own explanation and feeds **recognition**, not extra weight: each
  activity contributes at most one hit.
- `preferences`:
  - `max_tuition`, `preferred_size` — as before.
  - `scope` — `usa` | `international` | `both`. **Hard filter.**
  - `institution_type` — `Public` | `Private` | null. **Hard filter**, applied
    before ranking so a requested `top_k` still comes back full.
  - `regions[]`, `settings[]` — **soft**. They fold into the `fit` dimension at
    0.25 each; an empty list scores 1.0, identical to a full match. Schools
    outside a stated region still appear, ranked lower. Only 28 of 358 schools
    are rural, so treating these as filters would discard most of the catalog.
- `weights` — optional per-request overrides of the rubric weights.

**Removed, and not to be reintroduced:** `mbti` (v2.0.0 — replaced by
self-reported culture preferences, since inferring campus fit from a personality
type was unfounded) and `preferences.locations[]` (v4.0.0 — it compared a typed
string against `University.location` such as `"Cambridge, MA"`, so it could
never fire in practice).

## University (`score.schema.json` → `$defs.University`)

`id`, `unitid`, `name`, `country`, `location`, `region`, `setting`, `type`,
`avg_gpa`, `avg_sat`, `acceptance_rate` (0–1), `net_price`, `sticker_tuition`,
`enrollment`, `size`, `majors[]`, `culture`, `population`, `url`,
`net_price_calculator_url`, `details`, `provenance`. Persisted in the
`universities` table (`db/schema.sql`).

Notes that matter:

- `location` is **display-only** — never a filter, never a scoring input.
- `region` ∈ {Northeast, South, West, Midwest, International}; `setting` ∈
  {urban, suburban, rural}; `type` ∈ {Public, Private}. All three are editorial
  and present for all 358 schools.
- `population` — `{international_share, women_share, first_gen_share}` from
  College Scorecard, **US only**. It is `null` for all 90 non-US schools with
  `provenance.population = "not_applicable"`, because the federal dataset does
  not cover them. Individual shares can also be null where the source said
  `PrivacySuppressed`.
- `majors[]` holds a median of ~6 editorial **strengths**, not a course catalog.
  Absence from this list does **not** mean a school lacks the subject — deriving
  "what a school doesn't offer" from it would wrongly claim MIT has no
  Philosophy department. Scorecard's `PCIP*` columns are the honest route.
- `provenance` maps a field to `observed` | `web_verified` | `editorial` |
  `not_applicable` | `absent`.

## Scoring (`score.schema.json`)

`RankRequest {profile, weight_feedback, universities[]}` →
`RankResponse {scores[]}` where each `ScoredUniversity` has `university_id`,
`score` (0–1), and a per-component breakdown. Sorted by descending score, then
ascending `university_id`.

Six weighted dimensions: `academic` .28, `cost` .18, `fit` .18, `culture` .18,
`activities` .10, `personality` .08.

## Recommendation (`recommendation.schema.json`)

`RecommendationRequest {profile, max_iterations, top_k}` →
`RecommendationResponse {results[], confidence, stop_reason, trace[]}`. Each
`Result` carries a `university` summary and a server-computed `admit_tier`
(`reach` | `target` | `safety`).
`stop_reason ∈ {R1_converged, R2_confident, R3_no_change, R4_iteration_cap}`.
Persisted in the `recommendations` table.

## Mirrors (must move together)

`docs/contracts/*.json` ↔ `services/scoring-service/app/schemas.py` ↔
`services/recommendation-service/app/schemas.py` ↔
`services/gateway/src/types.ts` ↔ `college-recommender/lib/contract.ts`.

That last one lives outside `services/` and is the easiest to forget. Changing
one shape without the others (and a version bump) is contract drift (H3).
