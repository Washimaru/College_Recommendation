/**
 * Mirrors docs/contracts/{profile,recommendation}.schema.json v2.0.0.
 *
 * The gateway is the validating authority; these types keep the client honest
 * at compile time. There is deliberately no `mbti` field - it was removed in
 * v2.0.0 and replaced by self-reported culture preferences.
 */

export const CULTURE_AXES = [
  "collab",
  "quirky",
  "idealist",
  "research",
  "spirit",
  "seminar",
] as const;

export type CultureAxis = (typeof CULTURE_AXES)[number];

/** Slider labels, inherited verbatim from the original UniMatch project. */
export const AXIS_LABELS: Record<CultureAxis, { left: string; right: string }> = {
  collab: { left: "Hyper-competitive", right: "Collaborative & supportive" },
  quirky: { left: "Work-hard, play-hard", right: "Quirky & intellectual" },
  idealist: { left: "Careerist / pre-professional", right: "Idealist / mission-driven" },
  research: { left: "Hands-on, project & co-op", right: "Theory & research heavy" },
  spirit: { left: "Low-key sports scene", right: "Huge school spirit" },
  seminar: { left: "Big lectures & autonomy", right: "Small seminars & mentorship" },
};

export type CulturePrefs = Record<CultureAxis, number>;

/** 0.5 on every axis means "no preference", which the scorer treats as neutral. */
export const CENTRED_PREFS: CulturePrefs = Object.fromEntries(
  CULTURE_AXES.map((axis) => [axis, 0.5]),
) as CulturePrefs;

export type Provenance =
  | "observed"
  | "web_verified"
  | "editorial"
  | "not_applicable"
  | "absent";

export interface Profile {
  gpa: number;
  sat?: number | null;
  intended_major: string;
  culture_prefs?: CulturePrefs;
  preferences?: {
    max_tuition?: number | null;
    preferred_size?: "small" | "medium" | "large" | null;
    locations?: string[];
  };
}

export interface UniversitySummary {
  country: string;
  location: string;
  avg_gpa: number;
  avg_sat?: number | null;
  acceptance_rate?: number | null;
  net_price?: number | null;
  enrollment?: number | null;
  size: "small" | "medium" | "large";
  provenance: Partial<Record<string, Provenance>>;
}

export type AdmitTier = "reach" | "target" | "safety";

export interface Result {
  university_id: string;
  name: string;
  score: number;
  rationale: string;
  admit_tier?: AdmitTier | null;
  university: UniversitySummary;
}

export interface RecommendationResponse {
  results: Result[];
  confidence: number;
  stop_reason: string;
  trace: { iteration: number; confidence: number; stop_reason: string | null }[];
}
