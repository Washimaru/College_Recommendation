/**
 * Mirrors docs/contracts/{profile,recommendation}.schema.json v10.0.0.
 *
 * The gateway is the validating authority; these types keep the client honest
 * at compile time. Two fields are deliberately absent: `mbti`, removed in
 * v2.0.0 in favour of self-reported culture preferences, and
 * `preferences.locations`, removed in v4.0.0 because it compared a typed string
 * against `University.location` ("Cambridge, MA") and so could never fire.
 * `location` itself stays, for display only — never as a filter or a score.
 *
 * v5.0.0 adds `Profile.gpa_weighted` (displayed only, never scored — see
 * docs/superpowers/specs/2026-08-03-gpa-scales-tiers-and-profiles-design.md)
 * and the `extreme_reach` member of `AdmitTier`.
 *
 * v6.0.0 caps each `profile.weights` override at 1.0 and enforces the
 * `weight_feedback` clamp in scoring-service's own schema. Nothing changes
 * here: this client has never sent either field, and `Profile` below
 * deliberately still omits `weights` rather than mirroring a field the UI
 * has no control for.
 *
 * v7.0.0 adds `tuition_in_state` and `programs` to the university shape.
 * `programs` is federal PCIP data — the share of degrees a school actually
 * awards — and is the only field here that can support "this school does not
 * offer X". `majors` cannot: it names strengths, so absence from it means
 * nothing. `null` programs is "unmeasured"; `[]` is "measured, awards none of
 * these".
 *
 * v8.0.0 adds `University.state` and `preferences.home_state`. `net_price` at
 * a public university is the federal average for *in-state* students, so an
 * out-of-state applicant is quoted a resident's price unless they say where
 * they live. `state` is structured for exactly this reason — `location`
 * ("Ann Arbor, MI") is display-only and must never be parsed.
 *
 * v9.0.0 adds `University.notable_faculty` — named professors from Wikipedia
 * category membership plus Wikidata. No model produced them, so a name there
 * belongs to someone who exists; and the shape carries no email or phone,
 * which is why it can be published when the faculty CSVs cannot.
 *
 * v10.0.0 adds `University.active_faculty` — who is researching there *now*
 * and on what, from publication records. `notable_faculty` answers a different
 * question ("who is famous here") and includes people long dead, which is why
 * the two are separate fields and separate views.
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
  /** Client-side only: true when the last classify attempt couldn't reach the
   *  service at all — distinct from a successful check that recognised
   *  nothing. Not sent back. */
  checkFailed?: boolean;
}

export type ActivityKind =
  | "competition" | "club" | "volunteering" | "work"
  | "sport" | "arts" | "research" | "other";

/** Derived from the questionnaire, on axes the culture vector does not cover. */
export interface Personality {
  intensity: number;
  scale: number;
}

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
  /** Weighted GPA, 0.0-5.0. Displayed only — never scored, never converted to
   *  or from the unweighted `gpa` above. */
  gpa_weighted?: number | null;
  sat?: number | null;
  intended_major: string;
  culture_prefs?: CulturePrefs;
  personality?: Personality;
  activities?: Activity[];
  preferences?: {
    scope?: Scope;
    max_tuition?: number | null;
    /** Two-letter US state, if the student says. Only affects cost scoring. */
    home_state?: string | null;
    preferred_size?: "small" | "medium" | "large" | null;
    regions?: Region[];
    settings?: Setting[];
    institution_type?: InstitutionType | null;
  };
}

export interface Program {
  name: string;
  share: number;
}

export interface ActiveResearcher {
  name: string;
  /** Specific topics, e.g. "Mathematical Dynamics and Fractals". */
  research?: string[];
  /** Coarse fields, e.g. "Mathematics" — what the major filter matches on. */
  fields?: string[];
  /** Papers written from this school since the cutoff. */
  recent_works?: number | null;
  last_active?: number | null;
  source: "openalex" | "directory";
  source_url: string;
}

export interface NotableProfessor {
  name: string;
  /** One line on who they are, e.g. "American theoretical physicist". */
  known_for?: string | null;
  fields?: string[];
  /** "historical" = a recorded date of death, so never rendered as teaching now. */
  status: "current" | "historical";
  /** Language editions carrying an article — a measured proxy for renown. */
  prominence?: number;
  source: "wikipedia" | "directory";
  source_url: string;
}

export interface UniversitySummary {
  country: string;
  location: string;
  /** Two-letter US state code; null outside the US. */
  state?: string | null;
  region: Region;
  setting: Setting;
  type: InstitutionType;
  avg_gpa: number;
  avg_sat?: number | null;
  acceptance_rate?: number | null;
  net_price?: number | null;
  /** Out-of-state, which is simply the price at a private school. */
  sticker_tuition?: number | null;
  /** In-state; US only, and less than half of sticker_tuition at most publics. */
  tuition_in_state?: number | null;
  /** null = unmeasured; [] = measured and awards none of these families. */
  programs?: Program[] | null;
  /** null = nobody searched; [] = searched and found nobody. */
  notable_faculty?: NotableProfessor[] | null;
  /** Researching here now. Same null/[] rule. */
  active_faculty?: ActiveResearcher[] | null;
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
 * Curated profile sections. Coverage varies sharply by section (as of the
 * current catalog: research 253, scholarships 101, faculty 81, admissions 67,
 * academics 66, campus 61, outcomes 60, programs 59) — see
 * `WITH_DETAILS_COUNT` in `catalogStats.ts` for how many schools have any of
 * them, which is generated rather than typed in. Absent sections are simply
 * not rendered — never filled with a placeholder or a guess.
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

export type AdmitTier = "extreme_reach" | "reach" | "target" | "safety";

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
}
