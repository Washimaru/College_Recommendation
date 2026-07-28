# UniMatch

A college recommendation pipeline: a stateless TypeScript gateway in front of
two Python FastAPI services (deterministic scoring + a hybrid recommendation
loop), backed by Postgres and fed by a synthetic data pipeline.

## Quickstart

```bash
cp .env.example .env
./scripts/setup.sh                 # per-service venvs + gateway npm install
docker compose up -d db            # Postgres only (schema applies on first init)
PYBIN=.venv/bin/python ./scripts/verify.sh   # full gate → "VERIFY: GREEN"
./scripts/smoke.sh                 # compose up, seed, one end-to-end recommendation
```

## Layout

- `services/gateway` — Fastify REST + WS (stateless).
- `services/scoring-service` — deterministic `POST /rank`.
- `services/recommendation-service` — the runtime loop + writes to `recommendations`.
- `data-pipeline` — synthetic university generator + loader.
- `db/schema.sql` — the single schema (Python side owns it).
- `docs/` — architecture, data model, the loop engineering spec, integration.
- `docs/contracts/*.json` — the wire contracts (the "law").

See `docs/ARCHITECTURE.md` for the request flow and `docs/LOOP_ENGINEERING.md`
for the build loop and terminating conditions.
