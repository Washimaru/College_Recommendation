/**
 * Where this build is running.
 *
 * The full product needs four services — gateway, recommendation-service,
 * scoring-service and Postgres. GitHub Pages serves static files and nothing
 * else, so a Pages build can offer Browse, Major Finder and the college list
 * (all of which need only the catalog) but genuinely cannot run the matching
 * loop.
 *
 * Rather than let those pages fail at runtime and look broken, the build is
 * told which it is, and the affected pages say so plainly.
 */
export const IS_STATIC_DEMO = process.env.NEXT_PUBLIC_STATIC_DEMO === "1";

/** Repo-subpath prefix on Pages (`/College_Recommendation`), empty locally. */
export const BASE_PATH = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

/**
 * Where the catalog comes from.
 *
 * Locally it is proxied from the live gateway, so Browse always reflects
 * whatever is in Postgres. In a static build it is a JSON file generated from
 * the same `data-pipeline` sources at deploy time — one source of truth, two
 * delivery mechanisms.
 */
export const CATALOG_URL = IS_STATIC_DEMO
  ? `${BASE_PATH}/catalog.json`
  : "/api/universities";
