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
