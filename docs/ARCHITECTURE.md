# Architecture

Three deployable services plus a data pipeline, wired over HTTP. Postgres is
owned by the Python side.

## Services

- **services/gateway** — Node 20 + TypeScript + Fastify. User-facing REST + WS.
  Stateless, no direct DB access. Validates with zod (`src/types.ts`) and calls
  the Python services over HTTP.
- **services/scoring-service** — Python 3.11 + FastAPI. Deterministic scoring
  (`POST /rank`). No LLM, no randomness, no clock.
- **services/recommendation-service** — Python 3.11 + FastAPI. Hybrid engine +
  the runtime loop (`app/loop.py`). Sole owner of writes to `recommendations`.
- **data-pipeline** — synthetic university generator + Postgres loader.

## Request flow

```
client → gateway POST /v1/recommendations   (zod validate, src/types.ts)
       → recommendation-service POST /recommend
         └─ loop.run_loop: rank_fn → llm.review → sanitize_review → _stop_reason
              └─ scoring-service POST /rank   (deterministic; sort -score, then id)
       → RecommendationResponse {results, confidence, stop_reason, trace}
```

Streaming is the same chain over SSE→WS: recommendation-service emits one SSE
frame per iteration at `/recommend/stream`; `gateway/src/clients/recs.ts` parses
the frames and `gateway/src/ws.ts` relays each to the client, breaking on the
`final` event.

## Boundaries (do not cross)

- The gateway holds no state and never talks to Postgres.
- Scoring is deterministic: same `RankRequest` ⇒ same `RankResponse`.
- Safety lives in code (`loop.sanitize_review`), never in an LLM prompt.
- One schema owner. The schema is `db/schema.sql`, mounted into
  `docker-entrypoint-initdb.d` and applied only on first init of an empty volume.
