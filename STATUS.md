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
| P9 UI integration | DONE |
| Sub-project A Real university catalog | DONE |
| Sub-project B Next.js UI rebuild | DONE |
| Spec A Explore & Decide (contract v4.0.0) | DONE |

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

## Verification (2026-07-30) — Explore & Decide (spec A), contract v4.0.0

Thirteen planned tasks implemented, each reviewed for spec compliance and code
quality before the next began, then a whole-branch review.

- **T2** `PYBIN=.venv/bin/python scripts/verify.sh` → `VERIFY: GREEN`.
- **T3** scoring 99.17%, recommendation 95.26%, data-pipeline 56 tests (no
  floor configured there); gateway 96.27% statements (floor 70%);
  `college-recommender` 93 tests (no coverage tooling installed).
- **T4** `scripts/smoke.sh` → `SMOKE OK: R1_converged 5 results`; in Postgres:
  **358** universities, 358 with `region`, 268 with `population`, and **0**
  non-US schools carrying a population (all SQL `NULL`, never `'{}'`).

Contract **v4.0.0** across all four mirrors, verified field-by-field with no
drift. `preferences.locations` removed; `University` gained `region`, `setting`,
`type`, `population`, `url`, `net_price_calculator_url`.

Frontend: `app/page.tsx` went from 443 lines to four routes (`/`, `/browse`,
`/majors`, `/list`) sharing a `localStorage`-backed profile store.

### Defects found and fixed during this work

Notable because none were caught by the passing test suites that preceded them:

1. **The scorer ignored activity descriptions the UI said it recognised.**
   `classify_activity` read name + kind + description; `activity_fit` read only
   name + kind. A student could write an explanation, watch four subjects light
   up, and get an identical ranking. Both now share `_activity_text()`. The old
   parity test asserted the property only for `"FIRST Robotics"` — a name that
   already matches, so the test could not fail.
2. **A stale alias silently cost one school all its federal data.** A fresher
   Scorecard release renamed `"University at Albany"` to `"SUNY at Albany"`.
3. **A classify outage was displayed as "not recognised"**, inviting a student
   to rewrite an explanation nobody would read.
4. **`/majors` implied no school taught a subject** when the catalog was simply
   unreachable.
5. **Match results were lost on every navigation**, forcing a re-run of the most
   expensive operation in the system.
6. **The hero understated the model** — "4 scored dimensions" where there are 6,
   stale since v3.0.0.

### Known gaps, deliberately not built

- **`region` has no SQL `CHECK` constraint** while `setting` and `type` do.
  Pydantic's `Literal` guards it and the loader is the only writer; adding one
  needs a `docker compose down -v`.
- **A listed school leaving the catalog** renders from its stored snapshot
  rather than being marked unavailable.
- **Corrupt `localStorage`** falls back to empty state, as specified and tested,
  but shows no notice.
