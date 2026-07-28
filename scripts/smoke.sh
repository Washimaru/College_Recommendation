#!/usr/bin/env bash
# Bring the stack up, seed the DB, and request one end-to-end recommendation.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

: "${DATABASE_URL:=postgresql://unimatch:unimatch@localhost:5432/unimatch}"
: "${GATEWAY_URL:=http://localhost:8000}"
export DATABASE_URL

# generate/load need the data-pipeline deps (psycopg). Prefer its venv; bare
# python3 usually lacks them. Override with PYBIN=... if needed.
PYBIN="${PYBIN:-$ROOT/data-pipeline/.venv/bin/python}"
if [ ! -x "$PYBIN" ]; then
  echo "note: $PYBIN not found, falling back to python3 (run scripts/setup.sh first)"
  PYBIN=python3
fi

echo "== docker compose up =="
docker compose up -d --build

echo "== waiting for gateway health =="
for _ in $(seq 1 30); do
  if curl -fsS "$GATEWAY_URL/healthz" >/dev/null 2>&1; then break; fi
  sleep 2
done

echo "== seed universities =="
"$PYBIN" data-pipeline/generate.py --count 100 --seed 42 --out /tmp/unimatch_unis.json
"$PYBIN" data-pipeline/load.py --file /tmp/unimatch_unis.json

echo "== request a recommendation =="
RESP="$(curl -fsS -X POST "$GATEWAY_URL/v1/recommendations" \
  -H 'content-type: application/json' \
  -d '{"profile":{"gpa":3.8,"sat":1400,"mbti":"ENFP","intended_major":"Computer Science"},"top_k":5}')"
echo "$RESP"

echo "$RESP" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["results"], "no results"; assert d["stop_reason"].startswith("R"); print("SMOKE OK:", d["stop_reason"], len(d["results"]), "results")'
