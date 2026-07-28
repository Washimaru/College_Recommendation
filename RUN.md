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
```bash
docker compose up -d --build
python3 data-pipeline/generate.py --count 100 --seed 42 --out /tmp/unis.json
DATABASE_URL=postgresql://unimatch:unimatch@localhost:5432/unimatch \
  python3 data-pipeline/load.py --file /tmp/unis.json
curl -s -X POST http://localhost:8000/v1/recommendations \
  -H 'content-type: application/json' \
  -d '{"profile":{"gpa":3.8,"sat":1400,"mbti":"ENFP","intended_major":"Computer Science"},"top_k":5}'
```

## Tests / gates
```bash
PYBIN=.venv/bin/python ./scripts/verify.sh   # everything
./scripts/smoke.sh                            # end-to-end
```
