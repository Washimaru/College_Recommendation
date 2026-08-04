import { describe, expect, it } from "vitest";

import { analyseList, MAX_SUGGESTIONS, SAFETY_MAX, SAFETY_MIN, suggestGaps } from "./listAnalysis";
import type { AdmitTier, Result } from "./contract";
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

function listOf(
  reach: number,
  target: number,
  safety: number,
  extremeReach = 0,
): ListedSchool[] {
  return [
    ...Array.from({ length: reach }, (_, i) => school(`r${i}`, "reach")),
    ...Array.from({ length: target }, (_, i) => school(`t${i}`, "target")),
    ...Array.from({ length: safety }, (_, i) => school(`s${i}`, "safety")),
    ...Array.from({ length: extremeReach }, (_, i) => school(`er${i}`, "extreme_reach")),
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

  it("counts extreme reaches separately, not folded into reach", () => {
    const result = analyseList(listOf(8, 4, 0, 3));

    expect(result.extremeReach).toBe(3);
    expect(result.reach).toBe(8);
    expect(result.total).toBe(15);
  });

  it("still keys the safety floor off safety share alone - extreme reaches count toward the total like any other listed school, with no separate maths path", () => {
    // 3 safeties out of 20 (including 17 extreme reaches) is exactly the
    // 15% floor - same formula, same threshold as a list with no extreme
    // reaches at all, just a bigger denominator.
    expect(analyseList(listOf(0, 0, 3, 17)).needsMoreSafeties).toBe(false);
    expect(analyseList(listOf(0, 0, 2, 18)).needsMoreSafeties).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Gap suggestions
// ---------------------------------------------------------------------------

function result(id: string, tier: AdmitTier | null, score: number): Result {
  return {
    university_id: id,
    name: `School ${id}`,
    score,
    rationale: "because",
    admit_tier: tier,
    university: {
      country: "USA", location: "CA", region: "West", setting: "urban", type: "Private",
      avg_gpa: 3.7, size: "medium", majors: ["CS"], culture: CULTURE, provenance: {},
    },
  };
}

describe("suggestGaps", () => {
  it("suggests matched safeties when the list has too few", () => {
    const list = listOf(8, 4, 0);
    const matches = [result("s1", "safety", 0.92), result("s2", "safety", 0.88)];

    const gaps = suggestGaps(list, matches);

    expect(gaps.map((g) => g.id)).toEqual(["s1", "s2"]);
  });

  it("never suggests a school already on the list", () => {
    // The student has already chosen it; re-offering it is noise.
    const listed = school("s1", "safety");
    const matches = [result("s1", "safety", 0.92), result("s2", "safety", 0.88)];

    const gaps = suggestGaps([...listOf(8, 4, 0), listed], matches);

    expect(gaps.map((g) => g.id)).toEqual(["s2"]);
  });

  it("never invents a school — with no matches there are no suggestions", () => {
    // The spec is explicit: drawn only from schools the student has actually
    // been matched with, never a school they have shown no interest in.
    expect(suggestGaps(listOf(8, 4, 0), [])).toEqual([]);
  });

  it("suggests nothing when the list already has enough safeties", () => {
    const matches = [result("s1", "safety", 0.92)];

    expect(suggestGaps(listOf(8, 4, 3), matches)).toEqual([]);
  });

  it("suggests nothing for an empty list", () => {
    expect(suggestGaps([], [result("s1", "safety", 0.92)])).toEqual([]);
  });

  it("offers only safeties, not reaches or targets", () => {
    const matches = [
      result("r1", "reach", 0.99),
      result("t1", "target", 0.95),
      result("s1", "safety", 0.70),
    ];

    expect(suggestGaps(listOf(8, 4, 0), matches).map((g) => g.id)).toEqual(["s1"]);
  });

  it("ranks by fit, best first", () => {
    const matches = [
      result("s1", "safety", 0.71),
      result("s2", "safety", 0.93),
      result("s3", "safety", 0.82),
    ];

    expect(suggestGaps(listOf(8, 4, 0), matches).map((g) => g.id)).toEqual(["s2", "s3", "s1"]);
  });

  it("caps how many it offers, so the page stays a nudge not a catalog", () => {
    const matches = Array.from({ length: 9 }, (_, i) =>
      result(`s${i}`, "safety", 0.9 - i * 0.01),
    );

    expect(suggestGaps(listOf(8, 4, 0), matches)).toHaveLength(MAX_SUGGESTIONS);
  });

  it("carries the fit through so the UI can show it", () => {
    const gaps = suggestGaps(listOf(8, 4, 0), [result("s1", "safety", 0.92)]);

    expect(gaps[0].fit).toBe(0.92);
    expect(gaps[0].tier).toBe("safety");
  });
});
