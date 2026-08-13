import { describe, expect, it } from "vitest";

import { AdmitTierSchema, CONTRACT_VERSION, ProfileSchema } from "../src/types.js";

describe("contract v8.0.0", () => {
  it("reports version 8.0.0", () => {
    expect(CONTRACT_VERSION).toBe("8.0.0");
  });

  it("accepts a profile with no gpa_weighted", () => {
    const result = ProfileSchema.safeParse({ gpa: 3.8, intended_major: "Computer Science" });
    expect(result.success).toBe(true);
  });

  it("accepts gpa_weighted within 0.0-5.0", () => {
    const result = ProfileSchema.safeParse({
      gpa: 3.8,
      gpa_weighted: 4.42,
      intended_major: "Computer Science",
    });
    expect(result.success).toBe(true);
  });

  it("rejects gpa_weighted above 5.0", () => {
    const result = ProfileSchema.safeParse({
      gpa: 3.8,
      gpa_weighted: 5.1,
      intended_major: "Computer Science",
    });
    expect(result.success).toBe(false);
  });

  it("rejects negative gpa_weighted", () => {
    const result = ProfileSchema.safeParse({
      gpa: 3.8,
      gpa_weighted: -0.1,
      intended_major: "Computer Science",
    });
    expect(result.success).toBe(false);
  });

  it("admit tier enum includes extreme_reach alongside the original three", () => {
    for (const tier of ["extreme_reach", "reach", "target", "safety"]) {
      expect(AdmitTierSchema.safeParse(tier).success).toBe(true);
    }
  });

  describe("weight overrides are bounded", () => {
    const profile = { gpa: 3.8, intended_major: "Computer Science" };

    it("accepts a weight of 1.0, the whole share of the rubric", () => {
      const result = ProfileSchema.safeParse({ ...profile, weights: { cost: 1 } });
      expect(result.success).toBe(true);
    });

    it("rejects a weight above 1.0 at the edge of the system", () => {
      const result = ProfileSchema.safeParse({ ...profile, weights: { cost: 999999 } });
      expect(result.success).toBe(false);
    });

    it("bounds every dimension, not just cost", () => {
      for (const key of ["academic", "cost", "fit", "culture", "activities", "personality"]) {
        const result = ProfileSchema.safeParse({ ...profile, weights: { [key]: 2 } });
        expect(result.success, `${key} is unbounded`).toBe(false);
      }
    });

    it("still rejects a negative weight", () => {
      const result = ProfileSchema.safeParse({ ...profile, weights: { cost: -0.1 } });
      expect(result.success).toBe(false);
    });
  });
});

describe("home_state", () => {
  const profile = { gpa: 3.8, intended_major: "Computer Science" };

  it("accepts a two-letter state", () => {
    const result = ProfileSchema.safeParse({
      ...profile,
      preferences: { home_state: "MI" },
    });
    expect(result.success).toBe(true);
  });

  it("stays optional — the whole feature is opt-in", () => {
    expect(ProfileSchema.safeParse({ ...profile, preferences: {} }).success).toBe(true);
  });

  it("rejects a full state name, which would silently never match", () => {
    const result = ProfileSchema.safeParse({
      ...profile,
      preferences: { home_state: "Michigan" },
    });
    expect(result.success).toBe(false);
  });
});
