import { describe, expect, it } from "vitest";

import { researchersIn, researchFamilies } from "./facultyByField";

/**
 * The active-faculty list carries OpenAlex research fields ("Mathematics",
 * "Physics and Astronomy") rather than Wikidata occupations, so matching a
 * major to them is a different mapping — the same idea, a different vocabulary.
 */
describe("researchersIn", () => {
  const RESEARCHERS = [
    { name: "Jim Wiseman", fields: ["Mathematics"], research: ["Fractals"],
      source: "openalex" as const, source_url: "https://openalex.org/A1" },
    { name: "Eve Economist", fields: ["Economics, Econometrics and Finance"], research: [],
      source: "openalex" as const, source_url: "https://openalex.org/A2" },
    { name: "Uma Unmapped", fields: ["Some New Field"], research: [],
      source: "openalex" as const, source_url: "https://openalex.org/A3" },
  ];

  it("matches a mathematician to Mathematics & Statistics", () => {
    expect(researchersIn(RESEARCHERS, "Mathematics & Statistics").map((p) => p.name))
      .toEqual(["Jim Wiseman"]);
  });

  it("matches an economist to Social Sciences", () => {
    expect(researchersIn(RESEARCHERS, "Social Sciences").map((p) => p.name))
      .toEqual(["Eve Economist"]);
  });

  it("never files someone under a field the mapping does not know", () => {
    const all = ["Mathematics & Statistics", "Social Sciences", "Visual & Performing Arts"]
      .flatMap((f) => researchersIn(RESEARCHERS, f).map((p) => p.name));

    expect(all).not.toContain("Uma Unmapped");
  });
});

describe("researchFamilies", () => {
  it("offers only families the school teaches and has researchers in", () => {
    const researchers = [
      { name: "Jim", fields: ["Mathematics"], research: [],
        source: "openalex" as const, source_url: "https://openalex.org/A1" },
    ];
    const programs = [
      { name: "Mathematics & Statistics", share: 0.1 },
      { name: "Agriculture", share: 0.2 },
    ];

    expect(researchFamilies(researchers, programs)).toEqual(["Mathematics & Statistics"]);
  });
});
