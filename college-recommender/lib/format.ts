/**
 * Rendering rules for values that may legitimately be absent.
 *
 * The catalog distinguishes "we observed this", "this does not apply here"
 * (e.g. the SAT outside the US) and "we don't know". Collapsing those into a
 * blank or a zero would throw away the entire point of the data model - and
 * would tell a student a school costs nothing when the truth is unknown.
 */
import type { AdmitTier, Provenance } from "./contract";

export type StatKind = "percent" | "money" | "number" | "decimal" | "score";

export interface RenderedStat {
  text: string;
  /** Short qualifier shown beside the value, e.g. "est." */
  note: string | null;
}

const NOTES: Partial<Record<Provenance, string>> = {
  editorial: "est.",
  web_verified: "verified",
};

function formatValue(value: number, kind: StatKind): string {
  if (kind === "percent") return `${Math.round(value * 100)}%`;
  if (kind === "money") return `$${Math.round(value).toLocaleString("en-US")}`;
  // GPAs must keep their decimals: 3.95 shown as "4" misstates selectivity.
  if (kind === "decimal") return value.toFixed(2);
  // Test scores are written without separators - "1,550" is not an SAT score.
  if (kind === "score") return String(Math.round(value));
  return Math.round(value).toLocaleString("en-US");
}

export function formatStat(
  value: number | null | undefined,
  provenance: Provenance | undefined,
  kind: StatKind,
): RenderedStat {
  if (value === null || value === undefined) {
    // A deliberate "does not apply" must read differently from a gap, so that
    // nobody later "fixes" it by inventing a number.
    if (provenance === "not_applicable") {
      return { text: "n/a", note: "not used at this school" };
    }
    return { text: "—", note: null };
  }
  return { text: formatValue(value, kind), note: NOTES[provenance ?? "absent"] ?? null };
}

export function tierLabel(tier: AdmitTier | null | undefined): string | null {
  if (!tier) return null;
  return {
    extreme_reach: "Extreme reach",
    reach: "Reach",
    target: "Target",
    safety: "Safety",
  }[tier];
}
