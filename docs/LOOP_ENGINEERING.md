# Loop Engineering (authoritative)

This document is the source of truth for how the build loop runs and when it
stops. The root `CLAUDE.md` summarizes it; on any conflict, this file wins.

## Constants

| Name | Value | Meaning |
|------|-------|---------|
| `MAX_FIX_ATTEMPTS` | 3 | Retries allowed to turn a red phase green before it is BLOCKED. |
| `MAX_BUILD_ITERATIONS` | 40 | Hard cap on build-loop turns. |
| Python coverage floor | 80% | Enforced via `--cov-fail-under=80`. |
| TS coverage floor | 70% | Enforced via `vitest.config.ts` thresholds. |

## Procedure (every turn)

1. `cat STATUS.md`; find the first phase not `DONE`.
2. Read its Definition of Done in `BUILD_PLAN.md` and the nearest `CLAUDE.md`.
3. Make the smallest change that satisfies the DoD.
4. Run the phase verify command; past phase 0 also run `scripts/verify.sh`.
5. Green → mark the phase `DONE`, append a changelog line. Red → fix and retry,
   at most `MAX_FIX_ATTEMPTS`.
6. Still red after 3 → mark `BLOCKED` with the failing output, STOP, report.

## Terminating conditions (complete only when ALL hold)

- **T1** every phase in `STATUS.md` is `DONE`.
- **T2** `scripts/verify.sh` exits 0 (prints `VERIFY: GREEN`).
- **T3** coverage floors met (py ≥ 80%, ts ≥ 70%).
- **T4** `scripts/smoke.sh` returns a valid recommendation.

## Halt-for-human conditions (stop immediately on ANY)

- **H1** a phase is `BLOCKED`.
- **H2** no progress across two turns running.
- **H3** contract drift: a `docs/contracts/*.json` shape changed without a
  version bump and matching updates to all three mirrors.
- **H4** `MAX_BUILD_ITERATIONS` reached.
