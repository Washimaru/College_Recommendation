/**
 * The generated counts must match the catalog they claim to describe.
 *
 * `lib/catalogStats.ts` is committed; the catalog it was generated from is a
 * gitignored build artifact. That gap is exactly how "358 universities" stayed
 * on every page of the site while the number itself had already moved on
 * elsewhere. This reads whichever real catalog is on disk and checks.
 */
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { CATALOG_SIZE, RURAL_COUNT, WITH_DETAILS_COUNT } from "./catalogStats";

interface CatalogRecord {
  setting?: string;
  details?: unknown;
}

/** Either the pipeline's own output or the copy the static demo is built from.
 *  CI regenerates the first before running this suite. */
const CANDIDATES = [
  join(__dirname, "..", "..", "data-pipeline", "out", "universities.json"),
  join(__dirname, "..", "public", "catalog.json"),
];

function loadCatalog(): CatalogRecord[] | null {
  for (const path of CANDIDATES) {
    if (!existsSync(path)) continue;
    const body = JSON.parse(readFileSync(path, "utf8"));
    return (Array.isArray(body) ? body : body.universities) as CatalogRecord[];
  }
  return null;
}

const catalog = loadCatalog();

describe("catalogStats", () => {
  it("exports counts that are plausible on their own", () => {
    expect(CATALOG_SIZE).toBeGreaterThan(0);
    expect(RURAL_COUNT).toBeLessThanOrEqual(CATALOG_SIZE);
    expect(WITH_DETAILS_COUNT).toBeLessThanOrEqual(CATALOG_SIZE);
  });

  describe.skipIf(catalog === null)("against the catalog on disk", () => {
    it("counts every school", () => {
      expect(CATALOG_SIZE).toBe(catalog!.length);
    });

    it("counts the rural schools", () => {
      const rural = catalog!.filter((record) => record.setting === "rural").length;
      expect(RURAL_COUNT).toBe(rural);
    });

    it("counts the schools with a curated profile", () => {
      const withDetails = catalog!.filter((record) => {
        const details = record.details;
        return details != null && Object.keys(details as object).length > 0;
      }).length;
      expect(WITH_DETAILS_COUNT).toBe(withDetails);
    });
  });
});
