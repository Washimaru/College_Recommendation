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

# Fail on the actual problem rather than 40 lines of "cannot connect to the
# Docker daemon" from the first compose call.
if ! docker info >/dev/null 2>&1; then
  echo "error: the Docker daemon is not running." >&2
  echo "  macOS:  open -a Docker      (then wait for the whale icon to settle)" >&2
  echo "  Linux:  sudo systemctl start docker" >&2
  exit 1
fi

echo "== docker compose up =="
# --wait blocks until every healthcheck passes, including the gateway's own
# (nothing depends_on the gateway, so plain `up -d` returns while it is still
# starting and the first request fails to connect).
docker compose up -d --build --wait

echo "== waiting for gateway health =="
ready=""
for _ in $(seq 1 30); do
  if curl -fsS "$GATEWAY_URL/healthz" >/dev/null 2>&1; then ready=1; break; fi
  sleep 2
done
if [ -z "$ready" ]; then
  # Carrying on here used to surface as a confusing curl error further down.
  echo "error: gateway never became healthy at $GATEWAY_URL after 60s." >&2
  docker compose ps >&2
  docker compose logs --tail 30 gateway recommendation-service scoring-service >&2
  exit 1
fi

echo "== build and seed the real catalog =="
# Offline: build_catalog reads the committed tier files, no network needed.
( cd "$ROOT/data-pipeline" && "$PYBIN" build_catalog.py )
( cd "$ROOT/data-pipeline" && "$PYBIN" load.py )

echo "== request a recommendation =="
RESP="$(curl -fsS -X POST "$GATEWAY_URL/v1/recommendations" \
  -H 'content-type: application/json' \
  -d '{"profile":{"gpa":3.8,"sat":1400,"intended_major":"Computer Science","culture_prefs":{"research":0.9,"collab":0.8}},"top_k":5}')"
echo "$RESP"

echo "$RESP" | python3 -c 'import sys,json; d=json.load(sys.stdin); assert d["results"], "no results"; assert d["stop_reason"].startswith("R"); print("SMOKE OK:", d["stop_reason"], len(d["results"]), "results")'
