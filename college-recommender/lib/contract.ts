/**
 * Mirrors docs/contracts/{profile,recommendation}.schema.json v4.0.0.
 *
 * The gateway is the validating authority; these types keep the client honest
 * at compile time. Two fields are deliberately absent: `mbti`, removed in
 * v2.0.0 in favour of self-reported culture preferences, and
 * `preferences.locations`, removed in v4.0.0 because it compared a typed string
 * against `University.location` ("Cambridge, MA") and so could never fire.
 * `location` itself stays, for display only — never as a filter or a score.
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

export interface Activity {
  name: string;
  kind: ActivityKind;
  years?: number | null;
  description?: string | null;
  /** Client-side only: what the classify endpoint recognised. Not sent back. */
  subjects?: string[];
}

export type ActivityKind =
  | "competition" | "club" | "volunteering" | "work"
  | "sport" | "arts" | "research" | "other";

/** Derived from the questionnaire, on axes the culture vector does not cover. */
export interface Personality {
  intensity: number;
  scale: number;
}

export const NEUTRAL_PERSONALITY: Personality = { intensity: 0.5, scale: 0.5 };

export type Scope = "usa" | "international" | "both";

export type Region = "Northeast" | "South" | "West" | "Midwest" | "International";
export type Setting = "urban" | "suburban" | "rural";
export type InstitutionType = "Public" | "Private";

export interface Population {
  international_share?: number | null;
  women_share?: number | null;
  first_gen_share?: number | null;
}

export interface Profile {
  gpa: number;
  sat?: number | null;
  intended_major: string;
  culture_prefs?: CulturePrefs;
  personality?: Personality;
  activities?: Activity[];
  preferences?: {
    scope?: Scope;
    max_tuition?: number | null;
    preferred_size?: "small" | "medium" | "large" | null;
    regions?: Region[];
    settings?: Setting[];
    institution_type?: InstitutionType | null;
  };
}

export interface UniversitySummary {
  country: string;
  location: string;
  region: Region;
  setting: Setting;
  type: InstitutionType;
  avg_gpa: number;
  avg_sat?: number | null;
  acceptance_rate?: number | null;
  net_price?: number | null;
  enrollment?: number | null;
  size: "small" | "medium" | "large";
  majors: string[];
  culture: Record<CultureAxis, number>;
  population?: Population | null;
  url?: string | null;
  net_price_calculator_url?: string | null;
  /** Curated per-school profile; null when none exists. Sections are heterogeneous. */
  details?: SchoolDetails | null;
  provenance: Partial<Record<string, Provenance>>;
}

/**
 * Curated profile sections. Only ~67 of 364 schools have any, and coverage
 * varies sharply by section (outcomes 60, research 29, scholarships 17,
 * grad/professional schools 6-7). Absent sections are simply not rendered.
 */
export interface SchoolDetails {
  scholarships?: { policy?: string; named?: string[] };
  research?: { level?: string; undergrad?: string; areas?: string; note?: string };
  outcomes?: { gradRate?: string; salary?: string; employers?: string[]; paths?: string };
  gradSchools?: string | string[];
  proSchools?: string | string[];
  aid?: string | { policy?: string; note?: string };
  academics?: Record<string, unknown>;
  programs?: string | string[];
  studentLife?: string | string[];
  collaborations?: string | string[];
  faculty?: string | string[];
  src?: string[];
  [key: string]: unknown;
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

/** Full catalog record from GET /v1/universities, used by browse. */
export interface University extends UniversitySummary {
  id: string;
  unitid?: string | null;
  name: string;
  sticker_tuition?: number | null;
}
