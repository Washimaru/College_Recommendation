# scoring-service — CLAUDE.md

Python 3.11 + FastAPI. **Deterministic** scoring only. Overrides the root
`CLAUDE.md` within this directory.

## Hard rules

- No `random`, no clock (`time`/`datetime`), no LLM, no network calls in scoring.
- Same `RankRequest` ⇒ same `RankResponse`. `tests/test_scoring.py::test_determinism_same_input_same_output` guards this.
- `POST /rank` returns scores **sorted by `-score` then `university_id`**.
- `app/schemas.py` mirrors `docs/contracts/{profile,score}.schema.json`. Changing
  the shape here without the contract + other mirrors is contract drift (H3).

## Layout

- `app/scoring.py` — the weighted rubric. `DEFAULT_WEIGHTS`, MBTI→trait priors,
  per-component functions each returning `[0,1]`, `rank()` as the entry point.
- `app/main.py` — `GET /healthz`, `POST /rank`.

## Verify

```
.venv/bin/python -m pytest --cov=app -q      # floor: 80%
.venv/bin/python -m ruff check app
```
