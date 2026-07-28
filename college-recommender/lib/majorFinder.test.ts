/**
 * Major Finder scoring. Ported from the original project's recommend(), with
 * the MBTI term removed and its weight redistributed.
 */
import { describe, expect, it } from "vitest";

import { recommendMajors, WORK_AXES } from "./majorFinder";

const NEUTRAL = { people: 0.5, applied: 0.5, creative: 0.5 };

describe("recommendMajors", () => {
  it("ranks a major whose courses you took above one you didn't", () => {
    const ranked = recommendMajors({
      courses: new Set(["Computer Science", "Math", "Physics"]),
      activities: "",
      axes: NEUTRAL,
    });

    const cs = ranked.find((r) => r.major.name === "Computer Science")!;
    const art = ranked.find((r) => r.major.cat === "Arts")!;
    expect(cs.score).toBeGreaterThan(art.score);
  });

  it("rewards an activities match", () => {
    const withActivities = recommendMajors({
      courses: new Set(),
      activities: "robotics club and hackathons",
      axes: NEUTRAL,
    }).find((r) => r.major.name === "Computer Science")!;

    const without = recommendMajors({
      courses: new Set(),
      activities: "",
      axes: NEUTRAL,
    }).find((r) => r.major.name === "Computer Science")!;

    expect(withActivities.score).toBeGreaterThan(without.score);
  });

  it("matches activities case-insensitively", () => {
    const ranked = recommendMajors({
      courses: new Set(),
      activities: "ROBOTICS",
      axes: NEUTRAL,
    }).find((r) => r.major.name === "Computer Science")!;

    expect(ranked.reasons).toContain("matches your activities");
  });

  it("moves people-facing majors up when you say you prefer people", () => {
    const peopleFirst = recommendMajors({
      courses: new Set(),
      activities: "",
      axes: { people: 1, applied: 0.5, creative: 0.5 },
    });
    const thingsFirst = recommendMajors({
      courses: new Set(),
      activities: "",
      axes: { people: 0, applied: 0.5, creative: 0.5 },
    });

    expect(peopleFirst[0].major.axes.people).toBeGreaterThan(
      thingsFirst[0].major.axes.people,
    );
  });

  it("returns results sorted by descending score", () => {
    const scores = recommendMajors({
      courses: new Set(["Biology"]),
      activities: "",
      axes: NEUTRAL,
    }).map((r) => r.score);

    expect(scores).toEqual([...scores].sort((a, b) => b - a));
  });

  it("keeps every score within 0-100", () => {
    for (const ranked of [
      recommendMajors({ courses: new Set(), activities: "", axes: NEUTRAL }),
      recommendMajors({
        courses: new Set(["Math", "Physics", "Computer Science", "Biology"]),
        activities: "code robotics volunteering music",
        axes: { people: 1, applied: 1, creative: 1 },
      }),
    ]) {
      for (const r of ranked) {
        expect(r.score).toBeGreaterThanOrEqual(0);
        expect(r.score).toBeLessThanOrEqual(100);
      }
    }
  });

  it("explains itself with at most three reasons", () => {
    const top = recommendMajors({
      courses: new Set(["Computer Science", "Math", "Physics"]),
      activities: "robotics",
      axes: { people: 0.2, applied: 0.6, creative: 0.45 },
    })[0];

    expect(top.reasons.length).toBeGreaterThan(0);
    expect(top.reasons.length).toBeLessThanOrEqual(3);
  });

  it("never mentions MBTI, which was removed from the model", () => {
    const ranked = recommendMajors({
      courses: new Set(["Math"]),
      activities: "debate",
      axes: NEUTRAL,
    });

    for (const r of ranked) {
      for (const reason of r.reasons) {
        expect(reason.toLowerCase()).not.toContain("mbti");
        expect(reason.toLowerCase()).not.toContain("temperament");
      }
    }
  });
});

describe("WORK_AXES", () => {
  it("describes three axes with both poles labelled", () => {
    expect(WORK_AXES).toHaveLength(3);
    for (const axis of WORK_AXES) {
      expect(axis.left).toBeTruthy();
      expect(axis.right).toBeTruthy();
    }
  });
});
