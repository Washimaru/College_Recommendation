import { describe, expect, it } from "vitest";

import { analyseList, SAFETY_MAX, SAFETY_MIN } from "./listAnalysis";
import type { ListedSchool } from "./profileStore";

const CULTURE = { collab: 0.5, quirky: 0.5, idealist: 0.5, research: 0.5, spirit: 0.5, seminar: 0.5 };

function school(id: string, tier: ListedSchool["tier"]): ListedSchool {
  return {
    id,
    name: id,
    fit: 0.8,
    tier,
    university: {
      country: "USA", location: "CA", region: "West", setting: "urban", type: "Private",
      avg_gpa: 3.7, size: "medium", majors: ["CS"], culture: CULTURE, provenance: {},
    },
  };
}

function listOf(reach: number, target: number, safety: number): ListedSchool[] {
  return [
    ...Array.from({ length: reach }, (_, i) => school(`r${i}`, "reach")),
    ...Array.from({ length: target }, (_, i) => school(`t${i}`, "target")),
    ...Array.from({ length: safety }, (_, i) => school(`s${i}`, "safety")),
  ];
}

describe("analyseList", () => {
  it("counts each tier", () => {
    const result = analyseList(listOf(8, 4, 0));

    expect(result.total).toBe(12);
    expect(result.reach).toBe(8);
    expect(result.target).toBe(4);
    expect(result.safety).toBe(0);
  });

  it("flags a list with no safeties", () => {
    const result = analyseList(listOf(8, 4, 0));

    expect(result.needsMoreSafeties).toBe(true);
    expect(result.targetRange).toEqual([2, 2]);
  });

  it("does not flag a list already inside the band", () => {
    expect(analyseList(listOf(8, 4, 3)).needsMoreSafeties).toBe(false);
  });

  it("scales the target with list size", () => {
    expect(analyseList(listOf(16, 0, 4)).targetRange).toEqual([3, 4]);
  });

  it("returns zeroes for an empty list without dividing by zero", () => {
    const result = analyseList([]);

    expect(result.total).toBe(0);
    expect(result.safetyShare).toBe(0);
    expect(result.needsMoreSafeties).toBe(false);
  });

  it("counts entries with no tier separately rather than as safeties", () => {
    const result = analyseList([school("x", null)]);

    expect(result.unknown).toBe(1);
    expect(result.safety).toBe(0);
  });

  it("uses the stated 15-20% band", () => {
    expect([SAFETY_MIN, SAFETY_MAX]).toEqual([0.15, 0.2]);
  });
});
