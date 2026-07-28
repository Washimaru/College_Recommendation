---
name: synthetic-data
description: Generate synthetic universities (and profiles) with realistic, correlated distributions for the UniMatch data pipeline, and load them into Postgres.
---

# synthetic-data

`data-pipeline/generate.py` produces universities deterministically for a seed.
Selectivity drives the rest: lower `acceptance_rate` ⇒ higher `avg_sat`/`avg_gpa`
and higher `tuition`, with bounded Gaussian noise. Values are clamped to the
contract ranges (sat 900–1580, gpa 2.0–4.0, tuition 8k–65k). Names are unique;
`majors` is a sorted 2–4 sample.

- Generate: `python3 data-pipeline/generate.py --count 100 --seed 42 --out unis.json`
- Load: `DATABASE_URL=... python3 data-pipeline/load.py --file unis.json` (upsert by id).

Keep it deterministic per seed — tests depend on it. Randomness is allowed here
(this is the pipeline, not scoring).
