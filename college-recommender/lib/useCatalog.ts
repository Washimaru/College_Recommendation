"use client";

import { useEffect, useState } from "react";

import type { University } from "./contract";
import { CATALOG_URL, IS_STATIC_DEMO } from "./deployment";

/**
 * Module-level cache, shared by every component that calls `useCatalog`.
 *
 * The catalog is 468 KB, and Browse and Major Finder are now separate routes
 * that mount and unmount on navigation - a per-mount fetch (the pre-split
 * behaviour, when there was one page) would re-download the whole thing on
 * every visit. `inFlight` dedupes concurrent mounts (including React Strict
 * Mode's double effect in dev) onto a single request. A failed fetch is
 * deliberately never written to `cache` - caching a transient outage would
 * turn one bad connection into a permanent "no catalog" for the rest of the
 * page's life, with no way to retry short of a full reload.
 */
let cache: University[] | null = null;
let inFlight: Promise<University[]> | null = null;

function fetchCatalog(): Promise<University[]> {
  if (cache) return Promise.resolve(cache);
  if (!inFlight) {
    inFlight = fetch(CATALOG_URL)
      .then(async (res) => {
        if (!res.ok) throw new Error(String(res.status));
        return res.json();
      })
      .then((body) => {
        // The gateway wraps the list; the static file is the bare array.
        const universities = (Array.isArray(body) ? body : body.universities) as University[];
        cache = universities;
        return universities;
      })
      .finally(() => {
        inFlight = null;
      });
  }
  return inFlight;
}

/** Fetches the catalog once per page load (cached at module scope), however
 *  many times Browse and Major Finder each mount it across navigation. */
export function useCatalog() {
  const [catalog, setCatalog] = useState<University[] | null>(cache);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Already resolved by the lazy `useState(cache)` initializer above — cache
    // cannot change between that render and this effect firing, since nothing
    // else runs in between on a single thread. Calling setState here too
    // would just be a redundant, effect-body setState for no benefit.
    if (cache) return;
    let cancelled = false;
    fetchCatalog()
      .then((universities) => {
        if (!cancelled) setCatalog(universities);
      })
      .catch(() => {
        if (!cancelled) {
          setError(
            IS_STATIC_DEMO
              ? "Couldn't load the catalog file. Try reloading the page."
              : "Couldn't load the catalog. Is the stack running?",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { catalog, error };
}
