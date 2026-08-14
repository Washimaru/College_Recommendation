import { describe, expect, it } from "vitest";

import { professorsIn, familiesWithProfessors, OCCUPATIONS_BY_FAMILY } from "./facultyByField";
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
