import { describe, expect, it } from "vitest";

import type { University } from "./contract";
import { countriesOf, searchUniversities } from "./search";

const CULTURE = { collab: 0.5, quirky: 0.5, idealist: 0.5, research: 0.5, spirit: 0.5, seminar: 0.5 };

function uni(over: Partial<University>): University {
  return {
    id: "x", name: "X University", country: "USA", location: "Boston, MA",
    avg_gpa: 3.5, size: "medium", majors: ["Biology"], culture: CULTURE, provenance: {},
    ...over,
  } as University;
}

const CATALOG = [
  uni({ id: "berk", name: "University of California, Berkeley", location: "Berkeley, CA", majors: ["Computer Science"] }),
  uni({ id: "berklee", name: "Berklee College of Music", location: "Boston, MA", majors: ["Music"] }),
  uni({ id: "ox", name: "University of Oxford", country: "UK", location: "Oxford", majors: ["PPE"], size: "large" }),
];

describe("searchUniversities", () => {
  it("returns everything for an empty query", () => {
    expect(searchUniversities(CATALOG, "")).toHaveLength(3);
  });

  it("matches on name", () => {
    expect(searchUniversities(CATALOG, "berklee").map((u) => u.id)).toEqual(["berklee"]);
  });

  it("matches on city", () => {
    expect(searchUniversities(CATALOG, "boston").map((u) => u.id)).toEqual(["berklee"]);
  });

  it("matches on major, so a subject search works in the same box", () => {
    expect(searchUniversities(CATALOG, "music").map((u) => u.id)).toEqual(["berklee"]);
  });

  it("is case insensitive and ignores surrounding whitespace", () => {
    expect(searchUniversities(CATALOG, "  OXFORD ").map((u) => u.id)).toEqual(["ox"]);
  });

  it("filters by country", () => {
    expect(searchUniversities(CATALOG, "", { country: "UK" }).map((u) => u.id)).toEqual(["ox"]);
  });

  it("combines a query with a filter", () => {
    expect(searchUniversities(CATALOG, "university", { country: "UK" }).map((u) => u.id)).toEqual(["ox"]);
  });

  it("returns nothing when there is no match", () => {
    expect(searchUniversities(CATALOG, "zzzz")).toHaveLength(0);
  });
});

describe("countriesOf", () => {
  it("orders by school count, then alphabetically", () => {
    expect(countriesOf(CATALOG)).toEqual(["USA", "UK"]);
  });
});
