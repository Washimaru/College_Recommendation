# BUILD_PLAN

Phases are advanced one at a time. Each has a Definition of Done (DoD) and a
verify command. Past phase 0, also run `scripts/verify.sh`.

## P0 — Bootstrap
Scaffold the tree, scripts, `.env.example`, `docker-compose.yml`.
**DoD:** `scripts/setup.sh` creates per-service venvs + installs gateway deps;
`scripts/verify.sh` exists and is executable.

## P1 — Contracts (the law)
`docs/contracts/{profile,score,recommendation}.schema.json` plus the three
mirrors (`scoring-service/app/schemas.py`, `recommendation-service/app/schemas.py`,
`gateway/src/types.ts`).
**DoD:** all four agree; mirrors import/typecheck; contracts are valid JSON.

## P2 — Scoring service
Deterministic weighted rubric + MBTI priors; `POST /rank`, `GET /healthz`.
**DoD:** sorted by `-score` then id; determinism test passes; coverage ≥ 80%.
**Verify:** `cd services/scoring-service && .venv/bin/python -m pytest --cov=app -q`

## P3 — Recommendation loop
`app/loop.py`: `run_loop` (rank_fn → llm.review → sanitize_review → _stop_reason),
`sanitize_review` trust boundary, `_stop_reason` R1>R2>R3>R4, `MockLLM`.
**DoD:** `test_R4_iteration_cap` and each stop-reason test pass; coverage ≥ 80%.
**Verify:** `cd services/recommendation-service && .venv/bin/python -m pytest --cov=app -q`

## P4 — Recommendation API + streaming
`POST /recommend`, `POST /recommend/stream` (SSE), `GET /healthz`; writes to
`recommendations` behind `DATABASE_URL`.
**DoD:** endpoint tests pass; streaming emits per-iteration then a final frame.

## P5 — Gateway REST
Fastify `POST /v1/recommendations` with zod validation, `GET /healthz`.
**DoD:** invalid MBTI → 400; valid body proxies to recs; upstream failure → 502.
**Verify:** `cd services/gateway && npm run typecheck && npm run test`

## P6 — Gateway WebSocket relay
`src/clients/recs.ts` SSE parsing + `src/ws.ts` relay, breaking on `final`.
**DoD:** ws test relays frames and closes after `final`; coverage ≥ 70%.

## P7 — Data pipeline + schema
`data-pipeline/{generate,load}.py`, `db/schema.sql`.
**DoD:** generator deterministic per seed with realistic ranges; tests pass;
schema applies on empty-volume init.
**Verify:** `cd data-pipeline && .venv/bin/python -m pytest -q`

## P8 — Polish
ruff + eslint clean; coverage floors enforced; `scripts/verify.sh` prints
`VERIFY: GREEN`.
**DoD:** lint clean (run explicitly — the gate's ruff steps are advisory);
`scripts/verify.sh` green; `scripts/smoke.sh` returns a valid recommendation.
