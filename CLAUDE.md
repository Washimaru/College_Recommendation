# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository.

**UniMatch** — a college recommendation pipeline: a student profile in, a ranked
and explained list of universities out. Three services plus a data pipeline.

## Prime directive

Advance the build loop in `docs/LOOP_ENGINEERING.md` (authoritative — on any
conflict with this file, that document wins). One phase per turn from
`BUILD_PLAN.md`; keep `STATUS.md` current. Success requires all of T1–T4; halt
for a human on any of H1–H4. Never declare success without T1–T4.

## Current state

T1–T4 all hold as of 2026-07-30: `verify.sh` prints `VERIFY: GREEN`, coverage is
above every floor, and `smoke.sh` returns a real recommendation
(`SMOKE OK: R1_converged 5 results`) with **358 real universities** in Postgres
and a row written to `recommendations`. **P9 (UI integration) is done** — see
`docs/INTEGRATION.md`. Venvs exist; lint is clean in all four projects.

The catalog is real, not synthetic: 358 institutions across 26 countries, with
admissions, cost and outcome figures from the U.S. Dept. of Education College
Scorecard where they exist, and `null` everywhere they do not.

Two shipped features and the contract version arrived together in
`feat/real-university-catalog` (contract **v4.0.0**): place and student-body
fields on `University`, and the four-route frontend. **Treat any part of this
scaffold you haven't run as unproven** — the unit suites pass with the
integration stubbed out, so green tests alone never exercise the Docker or DB
paths.

### Provenance (explains oddities you'll notice)

This tree was **reconstructed from an earlier version of this CLAUDE.md** after
the working copy was found missing on disk. Consequences:

- The docs and code were generated to satisfy the documentation, so they agree
  with each other closely — but that agreement is not independent evidence of
  correctness. Verify against tests, not against prose.
- `college-recommender/` **was** a husk (only `node_modules/` and a gutted
  `.git`) and has since been rebuilt from scratch: Next.js 16 / React 19 /
  Tailwind 4, four routes (`/`, `/browse`, `/majors`, `/list`), three API
  proxies, and its own vitest suite. It has **no nested `.git`**. It reads
  `college-recommender/AGENTS.md`, which warns that this Next.js version has
  breaking changes — check `node_modules/next/dist/docs/` rather than trusting
  recalled App Router conventions.
- The repo root **is** a git repo now (`git init` was run on 2026-07-27, after the
  reconstruction), so edits are recoverable — but history starts at that point.
  Work happens on `feat/real-university-catalog`. Note `data-pipeline/out/` and
  `.superpowers/` are gitignored: the catalog is a build artifact, reproducible
  from the committed `data-pipeline/sources/` tier files.

## Commands

Bootstrap — nothing else runs before this:

```bash
./scripts/setup.sh          # per-service .venv + .[dev]; npm install for gateway
cp .env.example .env
docker compose up -d db     # Postgres only
./scripts/install-agent-kit.sh   # optional: skills + commands into .claude/
```

Gates:

```bash
PYBIN=.venv/bin/python ./scripts/verify.sh   # prints "VERIFY: GREEN" on success
./scripts/smoke.sh                           # compose up, seed, one e2e recommendation
```

Per-service, run from that service's directory:

```bash
cd services/scoring-service        && .venv/bin/python -m pytest -q
cd services/recommendation-service && .venv/bin/python -m pytest -q
cd data-pipeline                   && .venv/bin/python -m pytest -q
cd services/gateway                && npm run typecheck && npm test && npm run coverage
```

**Running a single Python test requires `--no-cov`.** Both service
`pyproject.toml`s put `--cov=app --cov-fail-under=80` in `addopts`, so a
narrowed run measures coverage over the whole app, falls under the floor, and
fails for a reason that has nothing to do with your test:

```bash
.venv/bin/python -m pytest tests/test_loop.py::test_R4_iteration_cap -q --no-cov
.venv/bin/python -m pytest -k sanitize -q --no-cov
npx vitest run test/ws.test.ts              # gateway, one file
npx vitest run -t "rejects an invalid MBTI" # gateway, one case
```

Lint (not enforced by the gate — see below):

```bash
cd services/scoring-service && .venv/bin/python -m ruff check app
cd services/gateway        && npm run lint
```

## Gate caveats

- `scripts/verify.sh` defaults to `PYBIN=python3`. Without an explicit
  `PYBIN=.venv/bin/python` it runs **system Python, not the venvs**, and fails on
  missing dependencies. The script says so in its own header comment.
- Both `ruff` steps in the gate end in `|| true`, and gateway `npm run lint` is
  not in the gate at all. **`VERIFY: GREEN` says nothing about lint** — P8's
  "lint clean" DoD must be confirmed by running the lint commands yourself.
- Coverage floors *are* enforced: `--cov-fail-under=80` via `addopts` for both
  Python services, and 70% lines/functions/branches/statements in
  `services/gateway/vitest.config.ts` (which writes reports to `/tmp/gw-coverage`).
- `scripts/smoke.sh` seeds using `data-pipeline/.venv/bin/python` (override with
  `PYBIN=`), because `psycopg` lives in that venv and not in system `python3`.
  It needs a running Docker daemon and takes a few minutes on a cold build.

## Architecture

```
client → gateway POST /v1/recommendations        (zod validate, src/types.ts)
       → recommendation-service POST /recommend
         └─ loop.run_loop: rank_fn → llm.review → sanitize_review → _stop_reason
              └─ scoring-service POST /rank      (deterministic; sort -score, then id)
       → RecommendationResponse {results, confidence, stop_reason, trace}
```

Streaming is the same chain over SSE→WS: recommendation-service emits one SSE
frame per iteration at `/recommend/stream`; `gateway/src/clients/recs.ts` parses
the frames and `gateway/src/ws.ts` relays each onward, breaking on `final`.

- `services/gateway` — Node 20 + TypeScript + Fastify. Stateless, no DB. Files:
  `server.ts` (builds the app; separate from `index.ts` so tests skip binding a
  port), `routes.ts`, `ws.ts`, `clients/recs.ts`, `types.ts`. **The gateway talks
  only to recommendation-service** — it has no scoring client and no DB client.
- `services/scoring-service` — Python 3.11 + FastAPI. Deterministic `POST /rank`.
- `services/recommendation-service` — Python 3.11 + FastAPI. Runtime loop; sole
  owner of writes to `recommendations`.
- `data-pipeline` — synthetic generator + loader.

Both Python services have their own `CLAUDE.md` that overrides this one inside
their directory; read it before editing there. The gateway and data-pipeline
have none.

### Boundaries (do not cross)

- The gateway holds no state and never touches Postgres.
- Scoring is deterministic: no `random`, no clock, no LLM, no network. Same
  `RankRequest` ⇒ same `RankResponse`.
- Safety lives in code (`loop.sanitize_review`), never in an LLM prompt.
- One schema owner. `db/schema.sql` is mounted into `docker-entrypoint-initdb.d`
  and **applies only on first init of an empty volume** — there is no Alembic.
  To re-apply after editing it: `docker compose down -v && docker compose up -d db`.
- **What the UI shows a student must be what the scorer does.** The activity
  pattern table `_ACTIVITY_SUBJECTS` exists in exactly one place
  (`scoring-service/app/scoring.py`); recommendation-service forwards to it over
  HTTP rather than keeping a copy. One table is not sufficient on its own —
  `classify_activity` and `activity_fit` must also read the *same text*, which is
  why both go through `_activity_text()`. They once did not, and a student could
  write an explanation, watch four subjects light up, and see their ranking not
  move at all. `tests/test_classify.py::TestScorerReadsTheSameText` guards this;
  note its cases deliberately use names that match nothing, because the property
  cannot fail on a name that already matches.
- `University.location` is display-only — never a filter, never a scoring input.
- **Region and setting are soft; institution type is hard.** `regions` and
  `settings` fold into `fit` (0.25 each) and only nudge ranking, so schools
  outside a stated region legitimately still appear. Only 28 of 358 schools are
  rural; a mild preference must not silently discard 92% of the catalog.
  `institution_type` and `scope` are the only preference filters.

## The runtime loop — its stop reasons are not what their names suggest

Defined in `services/recommendation-service/app/loop.py`. Read `_stop_reason`
before touching anything here; the identifiers are easy to misread:

| Reason | Fires when |
|--------|-----------|
| `R1_converged` | the LLM's kept ids **equal the current top-k ranking** (agreement, not confidence) |
| `R2_confident` | `confidence >= CONFIDENCE_THRESHOLD` (0.9) |
| `R3_no_change` | this iteration's top-k equals the previous iteration's |
| `R4_iteration_cap` | `iteration == max_iterations - 1` — unconditional hard cap |

Precedence is **R1 > R2 > R3 > R4**, first match wins, and `stop_reason` is the
full string (`"R1_converged"`), not `"R1"`. `CONFIDENCE_THRESHOLD` and the
`[0.5, 1.5]` weight clamp are **module constants in `loop.py`, not env vars**;
`max_iterations` (default 5) and `top_k` (default 5) come from the request body.

`run_loop` is the single generator both `iter_loop` (blocking) and the SSE
endpoint consume, so streaming and non-streaming results cannot diverge — keep
it that way. Note `docs/LOOP_ENGINEERING.md` documents only the *build* loop;
these runtime conditions live solely in code.

## Contracts are law

`docs/contracts/{profile,score,recommendation}.schema.json` (all `version`
**`10.0.0`**, draft-07, `additionalProperties: false`) are the source of truth.
**Four** mirrors must move with them, in the same change:

- `services/scoring-service/app/schemas.py`
- `services/recommendation-service/app/schemas.py`
- `services/gateway/src/types.ts`
- `college-recommender/lib/contract.ts` — easy to forget; it is the one outside
  `services/`

Changing a shape without a version bump and all four mirrors is contract drift
(H3) — stop and surface it.

What the recent versions changed:

**v10.0.0** added `University.active_faculty` — who researches at a school
*now* and on what, from OpenAlex publication records
(`faculty-pipeline`'s `active-faculty` stage). It exists because
`notable_faculty` answers a different question: its `status` field records only
whether a date of death is known, so it lists people who left decades ago, and
Wikidata gives "biologist" where a student wants "single-cell transcriptomics".
The two are separate fields and separate views in the UI. This one is counted
from publications, so it claims **no teaching appointment** — it misses faculty
who do not publish and includes some research staff; only the school's own
directory can say "Associate Professor of English".

**v9.0.0** added `University.notable_faculty` — named professors per US school,
from Wikipedia category membership plus Wikidata (`faculty-pipeline`'s
`notable` stage). Three properties make it publishable where the faculty CSVs
are not: **no LLM is involved**, so a name there belongs to someone who exists;
the shape carries **no email or phone** (an allowlist in `build_catalog.py`,
not a blocklist); and `status` labels historical faculty, so a professor who
died in 1984 never reads as teaching now. `null` means nobody searched — every
non-US school — and `[]` means searched and found nobody, which is a real
answer for a small college.

**v8.0.0** added `University.state` and `Preferences.home_state`. `net_price`
is the federal average and, at a public university, that measure covers
**in-state** students — so every out-of-state applicant was being quoted a
resident's price, in a dimension worth 18% of the score.
`scoring._out_of_state_premium` adds the published tuition gap for a student
who says where they live; it is a **stated adjustment**, never written into the
catalog and never shown as an observed figure. Unstated home state changes
nothing. `state` comes from Scorecard's STABBR and exists precisely so
residency is never decided by parsing `location`, which stays display-only.

**v7.0.0** added `University.tuition_in_state` and `University.programs`.
`sticker_tuition` is the *out-of-state* price (and simply the price at a
private school); for 111 of 113 public schools the in-state figure is less than
half of it, so showing one number alone misstated a public university by tens
of thousands. `programs` is the federal PCIP share of degrees a school actually
awards: `null` means unmeasured, `[]` means measured and awarding none of these
families. **It is the only field that can support "this school does not offer
X."** `majors` cannot — it lists strengths, so absence from it would have the
catalog claim MIT has no philosophy department (it awards 1.6% of its degrees
there).

**v6.0.0** bounded the public weight override. Each `profile.weights` field is
now `[0, 1]` — a weight is a share of the rubric, and scoring normalises by
their sum, so the old unbounded `{"cost": 999999}` made cost ~100% of every
score. `weight_feedback` is validated to `[0.5, 1.5]` in scoring-service's own
schema as well as clamped by the loop, because that service answers on its own
port and cannot rely on the caller having clamped.

**v5.0.0** added `Profile.gpa_weighted` (displayed only, never scored) and the
`extreme_reach` admit tier.

**v4.0.0**, still the most load-bearing:
`University` gained `region`, `setting`, `type`, `population`, `url` and
`net_price_calculator_url`; `Preferences` swapped `locations` for `regions`,
`settings` and `institution_type`; `Activity` gained `description`.
`preferences.locations` was **removed**, not deprecated — it compared a typed
string against `University.location` (`"Cambridge, MA"`) and could never fire.
`location` itself stays, for display only.

## Config

Ports: gateway **8000**, scoring 8001, recommendation 8002, Postgres 5432.

Env (`.env.example`): `DATABASE_URL`, `SCORING_SERVICE_URL`, `RECS_SERVICE_URL`,
`GATEWAY_URL`, `PORT`. Note the `_SERVICE_` infix — code reads
`SCORING_SERVICE_URL`/`RECS_SERVICE_URL`, and in-container defaults are the
compose service names.

**There is no LLM provider switch.** `MockLLM` is constructed directly in
`recommendation-service/app/main.py`; there are no `LLM_*` env vars and no real
provider. Everything runs offline by default. Adding a real provider means
implementing the `LLM` protocol in `app/llm.py` and injecting it — the
`sanitize_review` trust boundary must stay in front of it.

Postgres is optional at runtime: `candidates.py` falls back to the bundled
`app/seed_universities.json` when `DATABASE_URL` is unset, and `db.persist` is a
no-op. `psycopg` is an optional extra (`.[db]`) for recommendation-service, so
setting `DATABASE_URL` after a plain `.[dev]` install will fail on import.

## House style

- Python: type hints everywhere, Pydantic v2, `ruff` clean (`E,F,I,UP,B`,
  line-length 100, target py311), `pytest`.
- TS: `strict`, no `any` in exported signatures, `vitest`.
- Keep functions small and named after what they return.
- Every service exposes `GET /healthz`.
- Don't game the gates: never edit a test to make it pass instead of fixing the
  code, unless you can show the test is wrong — and note that in the changelog.
