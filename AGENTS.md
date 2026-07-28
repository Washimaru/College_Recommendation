# AGENTS

This repository is built by an autonomous loop. The operating manual is
`CLAUDE.md` at the repo root (and per-service `CLAUDE.md` files that override it
within their directories). The authoritative loop spec is
`docs/LOOP_ENGINEERING.md`.

Any agent working here should:

1. Read `CLAUDE.md`, then `cat STATUS.md` to find the first non-`DONE` phase.
2. Follow that phase's DoD in `BUILD_PLAN.md`; make the smallest change.
3. Run the phase verify command and, past phase 0, `scripts/verify.sh`
   (with `PYBIN=.venv/bin/python`).
4. Respect the contracts (`docs/contracts/*.json`) and their three mirrors —
   changing a shape without a version bump across all mirrors is drift (H3).
5. Keep scoring deterministic and keep LLM-output safety in
   `recommendation-service/app/loop.py:sanitize_review`, never in a prompt.
6. Stop and report on any halt condition (H1–H4).
