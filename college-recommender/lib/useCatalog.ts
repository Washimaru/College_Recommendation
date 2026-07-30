"use client";

import { useEffect, useState } from "react";

import type { University } from "./contract";

/** Fetches the catalog once per mount. Browse and Major Finder both need it. */
export function useCatalog() {
  const [catalog, setCatalog] = useState<University[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/universities")
      .then(async (res) => {
        if (!res.ok) throw new Error(String(res.status));
        return res.json();
      })
      .then((body) => {
        if (!cancelled) setCatalog(body.universities as University[]);
      })
      .catch(() => {
        if (!cancelled) setError("Couldn't load the catalog. Is the stack running?");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { catalog, error };
}
