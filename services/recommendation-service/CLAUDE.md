# recommendation-service — CLAUDE.md

Python 3.11 + FastAPI. Hybrid engine + the **runtime loop** (`app/loop.py`).
Sole owner of writes to the `recommendations` table. Overrides the root
`CLAUDE.md` within this directory.

## The loop (app/loop.py)

`run_loop` is the single source of truth and yields one event per iteration plus
a terminal `final` event. `iter_loop` (blocking) and `/recommend/stream` (SSE)
both consume it, so streaming and non-streaming cannot diverge.

Per iteration: `rank_fn(weight_feedback)` → `llm.review` → `sanitize_review` →
`_stop_reason`.

Two guarantees that must stay in CODE, never in a prompt:

- **`sanitize_review` is the trust boundary.** It drops ids not in the scorer's
  candidate set, dedupes preserving order, clamps `weight_feedback` to
  `[0.5, 1.5]`, and coerces confidence into `[0, 1]`.
- **`_stop_reason` precedence is R1 > R2 > R3 > R4**, in that fixed order. R4
  fires at `i == max_iterations - 1` and makes termination unconditional.

## Offline by default

The LLM is behind the `LLM` protocol with a deterministic `MockLLM`; unit tests
use it and never hit the network. `rank_fn` is injectable — tests pass a fake so
they never call scoring-service. Candidates come from Postgres when
`DATABASE_URL` is set, else from `app/seed_universities.json`.

## Verify

```
.venv/bin/python -m pytest --cov=app -q      # floor: 80%
.venv/bin/python -m ruff check app
```
