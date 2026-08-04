import { describe, expect, it } from "vitest";

import { AdmitTierSchema, CONTRACT_VERSION, ProfileSchema } from "../src/types.js";

describe("contract v5.0.0", () => {
  it("reports version 5.0.0", () => {
    expect(CONTRACT_VERSION).toBe("5.0.0");
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
});
