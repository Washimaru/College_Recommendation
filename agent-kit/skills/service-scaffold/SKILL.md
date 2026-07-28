---
name: service-scaffold
description: Conventions for adding a FastAPI service or a gateway route to UniMatch — health checks, schema mirrors, and offline-by-default testing.
---

# service-scaffold

Every service exposes `GET /healthz` returning `{"status":"ok"}`.

Python services: FastAPI + Pydantic v2, type hints everywhere, `ruff` clean,
`pytest` with `--cov-fail-under=80`. Mirror the relevant `docs/contracts/*.json`
in `app/schemas.py`. Keep external dependencies injectable so tests run offline
(the recommendation loop injects `rank_fn` and uses `MockLLM`).

Gateway (TS): Fastify, `strict` tsconfig, no `any` in exported signatures,
`vitest` with ≥ 70% coverage. Validate every request body with a zod schema from
`src/types.ts`. Build the app in `src/server.ts` (`buildServer`) so tests can
inject fakes without binding a port.

Changing a wire shape means editing all three mirrors + the contract JSON with a
version bump — otherwise it is contract drift (H3).
