/**
 * Major Finder scoring.
 *
 * Ported from the original UniMatch project's `recommend()`. The MBTI term is
 * removed - it carried 0.10 there, and the same reasoning that took MBTI out of
 * the school-matching model applies to suggesting a field of study. Its weight
 * is redistributed to courses and work-style axes, which are self-reported.
 */
import { MAJORS, type MajorSpec } from "./majorsData";

export interface WorkAxes {
  people: number;
  applied: number;
  creative: number;
}

export interface MajorFinderInput {
  courses: Set<string>;
  activities: string;
  axes: WorkAxes;
}

export interface RankedMajor {
  major: MajorSpec;
  /** 0-100. */
  score: number;
  reasons: string[];
}

/** How you like to work. Distinct from the campus-culture axes. */
export const WORK_AXES: {
  key: keyof WorkAxes;
  left: string;
  right: string;
}[] = [
  { key: "people", left: "Data & things", right: "People" },
  { key: "applied", left: "Theoretical & abstract", right: "Hands-on & applied" },
  { key: "creative", left: "Analytical & systematic", right: "Creative & expressive" },
];

// Sums to 1. The original was courses .40 / activities .20 / axes .30 / mbti .10.
const W_COURSES = 0.45;
const W_ACTIVITIES = 0.2;
const W_AXES = 0.35;

export function recommendMajors(input: MajorFinderInput): RankedMajor[] {
  const activities = input.activities.trim().toLowerCase();

  const ranked = MAJORS.map((major): RankedMajor => {
    const reasons: string[] = [];

    const overlap = major.courses.filter((course) => input.courses.has(course));
    const courseScore = major.courses.length ? overlap.length / major.courses.length : 0;
    if (overlap.length) reasons.push(`courses: ${overlap.slice(0, 3).join(", ")}`);

    const activityHit = activities !== "" && new RegExp(major.act, "i").test(activities);
    if (activityHit) reasons.push("matches your activities");

    const distance =
      (Math.abs(input.axes.people - major.axes.people) +
        Math.abs(input.axes.applied - major.axes.applied) +
        Math.abs(input.axes.creative - major.axes.creative)) /
      3;
    const axisScore = 1 - distance;
    if (axisScore >= 0.85) reasons.push("fits how you like to work");

    const score = Math.round(
      100 * (courseScore * W_COURSES + (activityHit ? 1 : 0) * W_ACTIVITIES + axisScore * W_AXES),
    );

    return { major, score, reasons: reasons.slice(0, 3) };
  });

  return ranked.sort((a, b) => b.score - a.score || a.major.name.localeCompare(b.major.name));
}
