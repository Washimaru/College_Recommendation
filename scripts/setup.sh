#!/usr/bin/env bash
# Create per-service virtualenvs + install deps, and npm install for the gateway.
# Nothing else runs before this. Requires python3.11+ and node20+.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"

setup_py() {
  local dir="$1"; shift
  echo ">> $dir"
  ( cd "$ROOT/$dir" && "$PY" -m venv .venv && .venv/bin/pip install --quiet --upgrade pip && .venv/bin/pip install --quiet "$@" )
}

setup_py services/scoring-service ".[dev]"
setup_py services/recommendation-service ".[dev]"
setup_py data-pipeline ".[dev]"

echo ">> services/gateway (npm install)"
( cd "$ROOT/services/gateway" && npm install --no-audit --no-fund )

echo "setup complete."
