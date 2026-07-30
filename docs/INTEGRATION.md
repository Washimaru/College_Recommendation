# Integration (P9 — done)

The UI is wired to the gateway. This document used to describe a proposal and
claimed the UI "invents schools"; that is no longer true, so it now records what
exists instead.

## What is actually wired

`college-recommender/` is a Next.js 16 / React 19 / Tailwind 4 app. It has **no
nested `.git`** — it is tracked by the repo root, which *is* a git repo.

Route Handlers proxy to the gateway, all server-side so `GATEWAY_URL` never
reaches the browser and the gateway needs no CORS:

| Route Handler | Gateway endpoint |
|---|---|
| `app/api/recommend/route.ts` | `POST /v1/recommendations` |
| `app/api/universities/route.ts` | `GET /v1/universities` |
| `app/api/classify/route.ts` (Task 11) | `POST /v1/activities/classify` |

`GATEWAY_URL` defaults to `http://localhost:8000` when unset, so `npm run dev`
works against `docker compose up -d` with no extra configuration.

## Failure states are distinguished, deliberately

`api/recommend` does not flatten upstream failures into one error, because "the
service is down", "your profile didn't validate" and "no school matched" need
different words in front of a student:

- gateway unreachable → **503** `gateway_unreachable` — must never look like
  "no results"
- gateway returned 400 → **400**, carrying the validation detail through
- any other upstream failure → **502** `upstream_error`
- success → the payload verbatim

Recognition degrades more softly: a classify failure returns 502 and the UI
shows nothing recognised rather than blocking activity entry. The scorer does
its own matching regardless.

## Contract

The UI mirrors contract **v4.0.0** in `lib/contract.ts`. Two fields named in the
original proposal no longer exist and must not be reintroduced:

- `mbti` — removed in v2.0.0, replaced by self-reported culture preferences.
- `preferences.locations` — removed in v4.0.0; it compared a typed string against
  `University.location` (`"Cambridge, MA"`), so it could never fire in practice.
  `location` itself remains, for display only — never a filter, never a score.

Streaming over `/v1/recommendations/ws` exists in the gateway but the UI does not
consume it.
