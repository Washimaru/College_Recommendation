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
| Faculty pipeline M0–M6 (five stages + `all`) | DONE |
| Improvement plan Phase 1 Correctness (contract v6.0.0) | DONE |
| Improvement plan Phase 2 Accessibility and trust | DONE |
| Improvement plan Phase 3 Finish the faculty pipeline | TODO |
| Improvement plan Phase 4 Product features (specs B, C) | TODO |

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

## Verification (2026-08-12) — improvement plan Phase 1, contract v6.0.0

Six correctness items from `~/.claude/plans/ignore-the-press-of-wild-reef.md`.

- **T2** `PYBIN=.venv/bin/python ./scripts/verify.sh` → `VERIFY: GREEN`.
- **T3** scoring 100.00% (94 tests), recommendation 95.98% (64), data-pipeline
  78 tests, gateway 96.31% statements (30), `college-recommender` 137 tests
  with coverage tooling now installed: 75.43% statements / 63.18% branches /
  61.18% functions / 76.93% lines, floors set at 70/70/60/60.
- **T4** `./scripts/smoke.sh` → `SMOKE OK: R1_converged 5 results`, 358
  universities loaded.
- Lint: `ruff check` clean in all three Python projects, `eslint` 0 errors
  0 warnings in both TypeScript projects.

### What changed

1. **An empty catalog was cached forever.** `load_universities()` fell back to
   the seed only on an *exception*, but an unseeded table returns `[]` — cached
   for the life of the process, serving zero schools with no error and no log
   line. Verified end to end on a fresh volume: before `load.py` the gateway now
   serves the 12-school seed and logs *"catalog query returned 0 universities"*;
   after `load.py`, with no restart, the same containers serve all 358.
2. **A test that could not fail.** `assert a != b or a == b` in
   `test_nullable_fields.py` stood guard over the honest-nulls behaviour while
   asserting nothing. Both replacements were confirmed to fail against a scorer
   that invents a missing SAT. `personality_fit`'s "does not invent" test was
   only checking a range; it now pins the neutral 0.5.
3. **Unknown provenance rendered as "verified profile"** — the *strongest*
   label, reached by fallthrough. Now only `web_verified` and `editorial` make
   a claim; anything else says nothing.
4. **The weight override was unbounded** (contract **v6.0.0**, all five
   mirrors). `{"weights": {"cost": 999999}}` made cost ~100% of every score;
   each weight is now `[0, 1]`, so the largest legal override takes 55% while
   the other five keep their defaults. `weight_feedback` is validated to
   `[0.5, 1.5]` in scoring-service's own schema, not just clamped by the loop.
5. **`358` was typed into five frontend files** and `364` survived in two
   others, while the catalog it describes is a regenerated artifact.
   `build_catalog.py` now generates `college-recommender/lib/catalogStats.ts`;
   `lib/catalogStats.test.ts` fails if it disagrees with the catalog on disk,
   and CI fails if a rebuild leaves the committed module stale.
6. **vitest could not see `app/`** — four routes and three API proxies, holding
   every 400/502/503 branch, had no tests and a test placed there would not have
   run. Glob widened (verified: the new files are not collected without it),
   27 tests added across the proxies and pages.

### Known gaps, deliberately not built

All three gaps recorded here — `region` having no SQL `CHECK`, a delisted school
rendering from its snapshot unmarked, and corrupt `localStorage` recovering
silently — were closed in Phase 2 below.

## Verification (2026-08-12) — improvement plan Phase 2, accessibility and trust

- **T2** `PYBIN=.venv/bin/python ./scripts/verify.sh` → `VERIFY: GREEN`.
- **T3** scoring 100.00% (100 tests), recommendation 95.98% (64),
  data-pipeline 78, gateway 96.31% (30), `college-recommender` 191 tests at
  80.32% statements / 68.67% branches / 66.37% functions / 82.21% lines.
- **T4** `./scripts/smoke.sh` → `SMOKE OK: R1_converged 5 results` against a
  volume recreated from the amended schema.
- Lint: ruff clean in all three Python projects; eslint clean in both
  TypeScript projects.

### What changed

1. **`aria-modal="true"` was a claim neither modal honoured.** `useFocusTrap`
   moves focus in, wraps Tab and Shift+Tab at the edges, handles Escape, and
   returns focus to whatever opened the dialog. `UniversityModal` and the
   compare dialog both use it; removing the ref from either one fails a test.
2. **Results rendered silently for a screen-reader user.** The form now carries
   a polite live region — mounted before submit, since a region added at the
   same moment as its text is not reliably announced — saying how many schools
   matched, or that none did. The error branch keeps its `role="alert"` and the
   region stays empty there, so a failure is announced once, not twice.
3. **Three stated rubric shares contradicted the code** (culture "20%" in the
   contract and a test docstring, academic "0.35" in another). All corrected to
   18% and 0.28, and `test_documented_weights.py` now fails on any share quoted
   in a contract that no dimension carries.
4. **Two Pages workflows deployed to the same environment** — `nextjs.yml`, the
   stock starter, is deleted. **Two lockfiles** — `pnpm-lock.yaml` is deleted,
   `package.json` declares `packageManager`, and the README says which.
5. **`tsc` needed a manual `find .next -name "* 2.*" -delete`** before it would
   pass, because file-sync copies in `.next/` duplicate every declaration.
   `tsconfig.json` excludes them; verified `tsc` still catches a real error.
6. **A school leaving the catalog** is now marked on the list, with its stored
   figures labelled a snapshot. An unreachable catalog deliberately marks
   nothing — the Phase 1 failure mode inverted.
7. **Corrupt `localStorage`** sets a session-only `storageRecovered` flag, and
   the shell explains the empty session on every route, dismissibly.
8. **`region` has a SQL `CHECK`** matching the Pydantic `Literal`. Verified: a
   bad region is rejected by Postgres, and all 358 rows load under it.
