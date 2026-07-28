---
description: Run the full UniMatch gate and report the result.
---

Run `PYBIN=.venv/bin/python scripts/verify.sh` and report whether it printed
`VERIFY: GREEN`. Then explicitly run the lint commands (`ruff check app` in each
Python service, `npm run lint` in the gateway) since the gate's ruff steps are
advisory (`|| true`) and gateway lint is not in the gate. Note coverage floors
(py ≥ 80%, ts ≥ 70%). Do not edit code — this is read-only verification.
