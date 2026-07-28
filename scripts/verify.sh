#!/usr/bin/env bash
# Full gate. Exit 0 and prints "VERIFY: GREEN" only if every check passes.
# NOTE: pass PYBIN=.venv/bin/python or it uses system python3 (see root CLAUDE.md).
# ruff steps are advisory here (|| true); gateway lint is NOT part of this gate.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYBIN="${PYBIN:-python3}"

echo "== scoring-service =="
( cd "$ROOT/services/scoring-service" && "$PYBIN" -m pytest --cov=app --cov-fail-under=80 -q )
( cd "$ROOT/services/scoring-service" && "$PYBIN" -m ruff check app || true )

echo "== recommendation-service =="
( cd "$ROOT/services/recommendation-service" && "$PYBIN" -m pytest --cov=app --cov-fail-under=80 -q )
( cd "$ROOT/services/recommendation-service" && "$PYBIN" -m ruff check app || true )

echo "== data-pipeline =="
( cd "$ROOT/data-pipeline" && "$PYBIN" -m pytest -q )

echo "== gateway =="
( cd "$ROOT/services/gateway" && npm run typecheck && npm run test && npm run coverage )

echo "VERIFY: GREEN"
