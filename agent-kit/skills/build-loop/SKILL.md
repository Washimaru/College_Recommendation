---
name: build-loop
description: The meta-procedure for driving the UniMatch build loop — advance one phase at a time from BUILD_PLAN.md, keep STATUS.md current, and stop on the terminating or halt conditions.
---

# build-loop

Drive the build one phase at a time.

1. `cat STATUS.md` → first phase not `DONE`.
2. Read its DoD in `BUILD_PLAN.md` and the nearest `CLAUDE.md`.
3. Make the smallest change that satisfies the DoD.
4. Run the phase verify command; past phase 0 also `PYBIN=.venv/bin/python scripts/verify.sh`.
5. Green → set the phase `DONE`, append a one-line changelog. Red → fix, retry ≤ `MAX_FIX_ATTEMPTS` (3).
6. Still red → mark `BLOCKED`, STOP, report.

Complete only on **T1–T4** (all phases DONE · verify green · coverage floors · smoke returns a recommendation). Halt for a human on **H1–H4** (blocked phase · no progress two turns · contract drift without a version bump · `MAX_BUILD_ITERATIONS`=40). Full text: `docs/LOOP_ENGINEERING.md`.
