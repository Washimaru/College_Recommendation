# Integration (proposed P9)

`college-recommender/` is a pre-existing Next.js UI. Its `/api/recommend` route
currently calls Claude directly with web search and invents schools; it is **not
wired to the gateway**. It carries its own `.git`; the repo root is not a git repo.

## Proposed wiring (do not start while P0–P8 are in flight)

1. Replace the ad-hoc logic in `college-recommender/app/api/recommend/route.ts`
   with a `fetch` to `GATEWAY_URL/v1/recommendations`.
2. Map the UI form to the `RecommendationRequest` contract (gpa, sat, mbti,
   intended_major, preferences).
3. Render `results[]` with `rationale`, and optionally stream via the WS route
   `/v1/recommendations/ws`.
4. Add `GATEWAY_URL` to the UI's environment.

No contract changes are required; the UI consumes the existing wire shapes.
