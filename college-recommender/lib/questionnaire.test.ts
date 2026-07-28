import { describe, expect, it } from "vitest";

import { foldAnswers, QUESTIONS } from "./questionnaire";

describe("QUESTIONS", () => {
  it("covers all six culture axes plus intensity and scale", () => {
    const culture = QUESTIONS.filter((q) => q.target.kind === "culture").map(
      (q) => q.target.axis,
    );
    const personality = QUESTIONS.filter((q) => q.target.kind === "personality").map(
      (q) => q.target.axis,
    );

    expect(new Set(culture)).toEqual(
      new Set(["collab", "quirky", "idealist", "research", "spirit", "seminar"]),
    );
    expect(new Set(personality)).toEqual(new Set(["intensity", "scale"]));
  });

  it("asks about preferences, never about a personality type", () => {
    for (const q of QUESTIONS) {
      const text = `${q.prompt} ${q.low} ${q.high}`.toLowerCase();
      expect(text).not.toContain("mbti");
      expect(text).not.toContain("introvert");
      expect(text).not.toContain("extrovert");
      expect(text).not.toContain("personality type");
    }
  });

  it("gives every question two distinct labelled ends", () => {
    for (const q of QUESTIONS) {
      expect(q.low).toBeTruthy();
      expect(q.high).toBeTruthy();
      expect(q.low).not.toBe(q.high);
    }
  });
});

describe("foldAnswers", () => {
  it("leaves everything neutral when nothing is answered", () => {
    const { culturePrefs, personality, answered } = foldAnswers({});

    expect(answered).toBe(0);
    expect(Object.values(culturePrefs).every((v) => v === 0.5)).toBe(true);
    expect(personality).toEqual({ intensity: 0.5, scale: 0.5 });
  });

  it("routes a culture answer to its axis and leaves the others neutral", () => {
    const { culturePrefs } = foldAnswers({ seminar: 1 });

    expect(culturePrefs.seminar).toBe(1);
    expect(culturePrefs.collab).toBe(0.5);
  });

  it("routes a personality answer without touching culture", () => {
    const { personality, culturePrefs } = foldAnswers({ intensity: 1 });

    expect(personality.intensity).toBe(1);
    expect(Object.values(culturePrefs).every((v) => v === 0.5)).toBe(true);
  });

  it("counts only the questions actually answered", () => {
    expect(foldAnswers({ collab: 0, spirit: 1 }).answered).toBe(2);
  });

  it("keeps a partially completed questionnaire usable", () => {
    const { culturePrefs, personality } = foldAnswers({ collab: 0 });

    expect(culturePrefs.collab).toBe(0);
    expect(personality.intensity).toBe(0.5);
  });
});
