# STATUS

Legend: `DONE` · `TODO` · `BLOCKED`

| Phase | Status |
|-------|--------|
| P0 Bootstrap | DONE |
| P1 Contracts | DONE |
| P2 Scoring service | DONE |
| P3 Recommendation loop | DONE |
| P4 Recommendation API + streaming | DONE |
| P5 Gateway REST | DONE |
| P6 Gateway WebSocket relay | DONE |
| P7 Data pipeline + schema | DONE |
| P8 Polish | DONE |
| P9 UI integration (proposed) | TODO |

## Changelog

- Reconstructed the full UniMatch scaffold from `CLAUDE.md` after the tree was
  found missing on disk (only `CLAUDE.md` + a husk `college-recommender/`
  remained; no evidence the prior scaffold ever existed here).
- P1: authored contracts + three mirrors (version 1.0.0), verified consistent.
- P2: scoring-service 11 tests pass, ruff clean, coverage 100%.
- P3/P4: recommendation-service 18 tests pass, ruff clean, coverage 94%.
- P5/P6: gateway 12 tests pass, tsc clean, eslint clean, coverage ~99% (funcs 100%).
- P7: data-pipeline 8 tests pass, ruff clean; db/schema.sql added.
- P8: lint clean across services; per-service `--cov-fail-under` met.
- 2026-07-27 P0/P7 — fixed four defects that made `setup.sh` and `smoke.sh`
  unrunnable as written (none had ever been executed):
  1. `data-pipeline/pyproject.toml` lacked `[build-system]`/`[tool.setuptools]`,
     so setuptools refused the flat layout (`generate`, `load`) → added
     `py-modules` (kebab-case; `py_modules` is rejected by pyproject validation).
  2. Both Python Dockerfiles ran `pip install .` before `COPY app ./app`, but
     `packages = ["app"]` needs the dir present → copy `app/` first.
  3. `smoke.sh` seeded via bare `python3`, which lacks `psycopg` → use the
     data-pipeline venv via `PYBIN`, matching `verify.sh`'s convention.
  4. Gateway `tsconfig.json` (`rootDir: "."`, `include: ["src","test"]`) emitted
     `dist/src/index.js` while the image runs `dist/index.js`, and compiled tests
     into the production image → added `tsconfig.build.json` (`rootDir: "src"`,
     src only) and pointed `npm run build` at it.

## Verification (2026-07-27) — T1–T4 all satisfied

Previously T2/T4 had never been executed here. They have now run end-to-end on a
Docker host, and four defects that blocked them were fixed (see changelog):

- **T2** `PYBIN=.venv/bin/python scripts/verify.sh` → `VERIFY: GREEN`.
- **T3** scoring 98.33%, recommendation 93.67% (floor 80%); gateway 99.23%
  statements / 91.42% branches / 100% functions (floor 70%).
- **T4** `scripts/smoke.sh` → `SMOKE OK: R1_converged 5 results`; verified in
  Postgres: 100 universities loaded, 1 row persisted to `recommendations`.

Lint was confirmed separately, since the gate's ruff steps are advisory and
gateway eslint is not in the gate: `ruff check .` clean in all three Python
projects; eslint 0 errors / 0 warnings across 10 files.

Environment note: venvs were built with Python 3.14.6 (`python3` here), while the
service images are `python:3.11-slim`.
