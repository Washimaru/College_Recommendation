# Running UniMatch

## Prerequisites
Python 3.11+, Node 20+, Docker (for Postgres and the smoke test).

## One-time setup
```bash
cp .env.example .env
./scripts/setup.sh
```

## Local dev (services individually)
```bash
# scoring-service
cd services/scoring-service && .venv/bin/uvicorn app.main:app --port 8001

# recommendation-service (offline: uses bundled seed if DATABASE_URL unset)
cd services/recommendation-service && .venv/bin/uvicorn app.main:app --port 8002

# gateway
cd services/gateway && npm run dev
```

## Full stack

Needs a running Docker daemon (`open -a Docker` on macOS). Each service defines
a healthcheck and `depends_on` waits for it, so the chain starts in order;
`--wait` additionally holds until the gateway itself is answering, which plain
`up -d` does not (nothing depends on the gateway, so compose returns while it
is still starting and the first request fails to connect).

```bash
docker compose up -d --build --wait

# Build the real 358-school catalog from the committed sources and load it.
# `out/` is gitignored, so this step is what fills an empty database.
cd data-pipeline
.venv/bin/python build_catalog.py
DATABASE_URL=postgresql://unimatch:unimatch@localhost:5432/unimatch \
  .venv/bin/python load.py
cd ..

curl -s -X POST http://localhost:8000/v1/recommendations \
  -H 'content-type: application/json' \
  -d '{"profile":{"gpa":3.8,"sat":1400,"intended_major":"Computer Science",
       "culture_prefs":{"research":0.9,"collab":0.8}},"top_k":5}'
```

Until `load.py` has run, the recommendation service serves the bundled
12-school seed and logs that it is doing so — an unseeded database is treated
as a failed load, never as a catalog of zero schools.

`./scripts/smoke.sh` does all of the above in one command.

## Tests / gates
```bash
PYBIN=.venv/bin/python ./scripts/verify.sh   # everything
./scripts/smoke.sh                            # end-to-end
```
