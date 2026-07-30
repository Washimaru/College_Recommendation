import type { Result } from "./contract";
import type { ListedSchool } from "./profileStore";

/**
 * Balance of a student's college list.
 *
 * The 15-20% safety band is a stated preference, not a measured finding, and
 * copy presenting it must say so. Only the safety floor is checked: a list of
 * 20 reaches and 4 safeties passes, because over-reaching is a choice a student
 * is entitled to make knowingly.
 */
export const SAFETY_MIN = 0.15;
export const SAFETY_MAX = 0.2;

export interface ListAnalysis {
  total: number;
  reach: number;
  target: number;
  safety: number;
  /** Entries whose tier could not be computed, because no GPA was given. */
  unknown: number;
  safetyShare: number;
  targetRange: [number, number];
  needsMoreSafeties: boolean;
}

export function analyseList(list: ListedSchool[]): ListAnalysis {
  const total = list.length;
  const count = (tier: string) => list.filter((s) => s.tier === tier).length;
  const reach = count("reach");
  const target = count("target");
  const safety = count("safety");
  const unknown = list.filter((s) => !s.tier).length;

  if (total === 0) {
    return {
      total: 0, reach: 0, target: 0, safety: 0, unknown: 0,
      safetyShare: 0, targetRange: [0, 0], needsMoreSafeties: false,
    };
  }

  const safetyShare = safety / total;
  const targetRange: [number, number] = [
    Math.round(total * SAFETY_MIN),
    Math.round(total * SAFETY_MAX),
  ];

  return {
    total, reach, target, safety, unknown,
    safetyShare,
    targetRange,
    needsMoreSafeties: safetyShare < SAFETY_MIN,
  };
}

/**
 * How many gap suggestions to offer at once.
 *
 * A handful, not a catalog: the point is to nudge a student who has no safeties
 * toward ones they already liked, not to re-run the whole recommendation on the
 * list page.
 */
export const MAX_SUGGESTIONS = 3;

/**
 * Schools from the student's own matches that would fill the safety gap.
 *
 * Two honesty constraints, both from the spec and both load-bearing:
 *
 *   - **Never invented.** Suggestions are drawn only from `matches` — schools
 *     this student was actually recommended. With no matches there are no
 *     suggestions, and the page says so rather than reaching into the catalog
 *     for schools they have shown no interest in.
 *   - **Never something already chosen.** A school on the list is filtered out;
 *     re-offering it reads as noise and makes the count wrong.
 *
 * Only the safety floor is served, mirroring `analyseList`: over-reaching is a
 * choice a student is entitled to make knowingly, so nothing here ever suggests
 * dropping a reach.
 */
export function suggestGaps(
  list: ListedSchool[],
  matches: Result[],
  limit: number = MAX_SUGGESTIONS,
): ListedSchool[] {
  if (!analyseList(list).needsMoreSafeties) return [];

  const listed = new Set(list.map((s) => s.id));

  return matches
    .filter((m) => m.admit_tier === "safety" && !listed.has(m.university_id))
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map((m) => ({
      id: m.university_id,
      name: m.name,
      fit: m.score,
      tier: m.admit_tier ?? null,
      university: m.university,
    }));
}
