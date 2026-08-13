import { describe, expect, it } from "vitest";

import { MAJORS } from "./majorsData";
import { awardsDegreesIn, familyCoverage, MAJOR_TO_CIP_FAMILY } from "./cipFamilies";

/**
 * The bridge between what a student calls a field and what the federal data
 * counts. Its whole value is the negative case: `majors` lists strengths, so
 * only `programs` can say a school awards nothing in an area — and only when
 * somebody actually measured it.
 */

describe("awardsDegreesIn", () => {
  it("is true when the family appears", () => {
    const school = { programs: [{ name: "Engineering", share: 0.27 }] };

    expect(awardsDegreesIn(school, "Engineering")).toBe(true);
  });

  it("is false when a measured school does not award it", () => {
    const school = { programs: [{ name: "Engineering", share: 0.27 }] };

    expect(awardsDegreesIn(school, "Agriculture")).toBe(false);
  });

  it("is null — not false — when nobody measured the school", () => {
    expect(awardsDegreesIn({ programs: null }, "Engineering")).toBeNull();
    expect(awardsDegreesIn({}, "Engineering")).toBeNull();
  });

  it("treats a measured school awarding nothing as a real no", () => {
    expect(awardsDegreesIn({ programs: [] }, "Engineering")).toBe(false);
  });
});

describe("familyCoverage", () => {
  const catalog = [
    { programs: [{ name: "Engineering", share: 0.3 }] },
    { programs: [{ name: "History", share: 0.1 }] },
    { programs: [] },
    { programs: null },
  ];

  it("counts who awards it, who does not, and who was never measured", () => {
    expect(familyCoverage(catalog, "Engineering")).toEqual({
      family: "Engineering",
      awarding: 1,
      none: 2,
      unmeasured: 1,
    });
  });

  it("never counts an unmeasured school as awarding none", () => {
    const { none, unmeasured } = familyCoverage([{ programs: null }], "Engineering");

    expect(none).toBe(0);
    expect(unmeasured).toBe(1);
  });
});

describe("the mapping", () => {
  it("only names families the pipeline actually emits", () => {
    // Guards against a typo silently producing "0 schools award this".
    const emitted = new Set([
      "Agriculture", "Natural Resources & Conservation", "Architecture",
      "Area, Ethnic & Gender Studies", "Communication & Journalism",
      "Communications Technologies", "Computer & Information Sciences",
      "Personal & Culinary Services", "Education", "Engineering",
      "Engineering Technologies", "Foreign Languages & Linguistics",
      "Family & Consumer Sciences", "Legal Studies", "English Language & Literature",
      "Liberal Arts & Humanities", "Library Science", "Biological & Biomedical Sciences",
      "Mathematics & Statistics", "Military Technologies", "Interdisciplinary Studies",
      "Parks, Recreation & Fitness", "Philosophy & Religious Studies",
      "Theology & Religious Vocations", "Physical Sciences", "Science Technologies",
      "Psychology", "Homeland Security & Law Enforcement",
      "Public Administration & Social Service", "Social Sciences", "Construction Trades",
      "Mechanic & Repair Technologies", "Precision Production",
      "Transportation & Materials Moving", "Visual & Performing Arts",
      "Health Professions", "Business, Management & Marketing", "History",
    ]);

    for (const family of Object.values(MAJOR_TO_CIP_FAMILY)) {
      expect(emitted.has(family), `${family} is not a CIP family the catalog emits`).toBe(true);
    }
  });

  it("only names majors the Major Finder actually offers", () => {
    const offered = new Set(MAJORS.map((major) => major.name));

    for (const major of Object.keys(MAJOR_TO_CIP_FAMILY)) {
      expect(offered.has(major), `${major} is not a Major Finder major`).toBe(true);
    }
  });
});
