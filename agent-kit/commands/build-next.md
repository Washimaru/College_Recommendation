---
description: Advance the UniMatch build loop by one phase.
---

Run the `build-loop` procedure for exactly one phase: read `STATUS.md`, take the
first phase not `DONE`, satisfy its DoD in `BUILD_PLAN.md` with the smallest
change, run the phase verify command and `PYBIN=.venv/bin/python scripts/verify.sh`,
then update `STATUS.md` (DONE or BLOCKED) and append a changelog line. Stop after
one phase, or immediately on any halt condition (H1–H4).
