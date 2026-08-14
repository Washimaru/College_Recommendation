import { describe, expect, it } from "vitest";

import {
  familiesWithProfessors,
  OCCUPATIONS_BY_FAMILY,
  professorsIn,
  researchersIn,
  researchFamilies,
} from "./facultyByField";
import type { NotableProfessor } from "./contract";

/**
 * Matching a professor to a field of study.
 *
 * The occupations come from Wikidata ("physicist", "economist", "composer");
 * the families come from the federal degree data ("Physical Sciences",
 * "Business, Management & Marketing"). Neither was designed for the other, so
 * this is a mapping — and the honest failure mode is silence: a professor
 * whose occupation is unknown to the map is shown under "all fields" and
 * never asserted to belong to one.
 */

function prof(name: string, fields: string[], known_for = ""): NotableProfessor {
  return {
    name, fields, known_for, status: "current", prominence: 5,
    source: "wikipedia", source_url: `https://en.wikipedia.org/wiki/${name}`,
  };
}

const FACULTY = [
  prof("Nora Physicist", ["physicist"]),
  prof("Chen Chemist", ["chemist", "academic"]),
  prof("Eve Economist", ["economist"]),
  prof("Cy Coder", ["computer scientist"]),
  prof("Pat Poet", ["poet", "novelist"]),
  prof("Sam Sculptor", ["sculptor", "painter"]),
  prof("Uma Unknown", ["ombudsman"]),
];

describe("professorsIn", () => {
  it("finds the physicists and chemists under Physical Sciences", () => {
    const names = professorsIn(FACULTY, "Physical Sciences").map((p) => p.name);

    expect(names).toContain("Nora Physicist");
    expect(names).toContain("Chen Chemist");
    expect(names).not.toContain("Eve Economist");
  });

  it("puts an economist under Social Sciences, not under Business", () => {
    expect(professorsIn(FACULTY, "Social Sciences").map((p) => p.name)).toContain("Eve Economist");
    expect(professorsIn(FACULTY, "Business, Management & Marketing")).toHaveLength(0);
  });

  it("matches a writer to English and an artist to Visual & Performing Arts", () => {
    expect(professorsIn(FACULTY, "English Language & Literature").map((p) => p.name))
      .toContain("Pat Poet");
    expect(professorsIn(FACULTY, "Visual & Performing Arts").map((p) => p.name))
      .toContain("Sam Sculptor");
  });

  it("returns nobody rather than a guess when no one matches", () => {
    expect(professorsIn(FACULTY, "Agriculture")).toEqual([]);
  });

  it("never claims an unmapped occupation belongs to a field", () => {
    const everywhere = Object.keys(OCCUPATIONS_BY_FAMILY).flatMap((family) =>
      professorsIn(FACULTY, family).map((p) => p.name),
    );

    expect(everywhere).not.toContain("Uma Unknown");
  });

  it("reads the known_for line when the occupation list is empty", () => {
    const faculty = [prof("Ada Only", [], "American mathematician and logician")];

    expect(professorsIn(faculty, "Mathematics & Statistics").map((p) => p.name))
      .toEqual(["Ada Only"]);
  });
});

describe("familiesWithProfessors", () => {
  it("offers only the families this school both teaches and has professors in", () => {
    const programs = [
      { name: "Physical Sciences", share: 0.2 },
      { name: "Agriculture", share: 0.1 },
    ];

    expect(familiesWithProfessors(FACULTY, programs)).toEqual(["Physical Sciences"]);
  });

  it("offers nothing when the school's degree data is missing", () => {
    expect(familiesWithProfessors(FACULTY, null)).toEqual([]);
  });
});

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
