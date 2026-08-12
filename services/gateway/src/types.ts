/**
 * Zod validators + TS types mirroring
 * docs/contracts/{profile,recommendation}.schema.json.
 *
 * This is one of the three contract mirrors (with the two schemas.py files).
 * Changing a shape here requires a version bump and matching edits on the
 * Python side — otherwise it is contract drift (H3).
 */
import { z } from "zod";

export const CONTRACT_VERSION = "7.0.0";

export const RegionSchema = z.enum([
  "Northeast",
  "South",
  "West",
  "Midwest",
  "International",
]);
export const SettingSchema = z.enum(["urban", "suburban", "rural"]);
export const InstitutionTypeSchema = z.enum(["Public", "Private"]);

/** Student-body composition. Absent for non-US schools. */
export const PopulationSchema = z
  .object({
    international_share: z.number().min(0).max(1).nullable().optional(),
    women_share: z.number().min(0).max(1).nullable().optional(),
    first_gen_share: z.number().min(0).max(1).nullable().optional(),
  })
  .strict();

/**
 * Six bipolar culture axes. 0.0 and 1.0 are opposite poles; 0.5 means the
 * student has no preference and the axis contributes nothing to the score.
 * Replaces the MBTI-derived personality dimension removed in v2.0.0.
 */
const axis = () => z.number().min(0).max(1).default(0.5);

export const CulturePrefsSchema = z
  .object({
    collab: axis(),
    quirky: axis(),
    idealist: axis(),
    research: axis(),
    spirit: axis(),
    seminar: axis(),
  })
  .strict();

/** Competitions, clubs and other commitments. */
export const ActivitySchema = z
  .object({
    name: z.string().min(1),
    kind: z
      .enum(["competition", "club", "volunteering", "work", "sport", "arts", "research", "other"])
      .default("other"),
    years: z.number().int().min(0).max(12).nullable().optional(),
    description: z.string().max(500).nullable().optional(),
  })
  .strict();

/**
 * Derived from the questionnaire, on axes the culture vector does not cover so
 * no signal is scored twice. 0.5 means no preference.
 */
export const PersonalitySchema = z
  .object({
    intensity: z.number().min(0).max(1).default(0.5),
    scale: z.number().min(0).max(1).default(0.5),
  })
  .strict();

export const PreferencesSchema = z
  .object({
    max_tuition: z.number().min(0).nullable().optional(),
    preferred_size: z.enum(["small", "medium", "large"]).nullable().optional(),
    /** Hard filter on which schools are considered, not a ranking signal. */
    scope: z.enum(["usa", "international", "both"]).optional(),
    regions: z.array(RegionSchema).optional(),
    settings: z.array(SettingSchema).optional(),
    institution_type: InstitutionTypeSchema.nullable().optional(),
  })
  .strict();

/** Each weight is a share of the rubric, so 1.0 is the ceiling. Scoring
 *  normalises by the sum, so an unbounded value would make one dimension the
 *  whole score. */
export const WeightsSchema = z
  .object({
    academic: z.number().min(0).max(1).optional(),
    cost: z.number().min(0).max(1).optional(),
    fit: z.number().min(0).max(1).optional(),
    culture: z.number().min(0).max(1).optional(),
    activities: z.number().min(0).max(1).optional(),
    personality: z.number().min(0).max(1).optional(),
  })
  .strict();

export const ProfileSchema = z
  .object({
    gpa: z.number().min(0).max(4.0),
    /** Weighted GPA. Displayed only - never scored, never converted to or from
     * the unweighted `gpa` above. */
    gpa_weighted: z.number().min(0).max(5.0).nullable().optional(),
    sat: z.number().int().min(400).max(1600).nullable().optional(),
    intended_major: z.string().min(1),
    culture_prefs: CulturePrefsSchema.optional(),
    personality: PersonalitySchema.optional(),
    activities: z.array(ActivitySchema).optional(),
    preferences: PreferencesSchema.optional(),
    weights: WeightsSchema.optional(),
  })
  .strict();

export const RecommendationRequestSchema = z
  .object({
    profile: ProfileSchema,
    max_iterations: z.number().int().min(1).max(20).default(5),
    top_k: z.number().int().min(1).max(50).default(5),
  })
  .strict();

export const CultureSchema = z
  .object({
    collab: z.number().min(0).max(1),
    quirky: z.number().min(0).max(1),
    idealist: z.number().min(0).max(1),
    research: z.number().min(0).max(1),
    spirit: z.number().min(0).max(1),
    seminar: z.number().min(0).max(1),
  })
  .strict();

export const ProvenanceSchema = z.enum([
  "observed",
  "web_verified",
  "editorial",
  "not_applicable",
  "absent",
]);

/**
 * Enough of the university to explain why it is listed. Nullable fields are
 * deliberate: `provenance` says whether a null means "does not apply here"
 * or "we don't know". Neither may render as a zero.
 */
/**
 * One 2-digit CIP family and the share of degrees awarded in it. Federal
 * PCIP data only — never the editorial `majors` list, which names strengths,
 * so absence from it proves nothing.
 */
export const ProgramSchema = z
  .object({
    name: z.string().min(1),
    share: z.number().min(0).max(1),
  })
  .strict();

export const UniversitySummarySchema = z
  .object({
    country: z.string(),
    location: z.string(),
    region: RegionSchema,
    setting: SettingSchema,
    type: InstitutionTypeSchema,
    population: PopulationSchema.nullable().optional(),
    url: z.string().nullable().optional(),
    net_price_calculator_url: z.string().nullable().optional(),
    avg_gpa: z.number().min(0).max(4.0),
    avg_sat: z.number().int().min(400).max(1600).nullable().optional(),
    acceptance_rate: z.number().min(0).max(1).nullable().optional(),
    net_price: z.number().min(0).nullable().optional(),
    /** Out-of-state, which is simply the price at a private school. */
    sticker_tuition: z.number().min(0).nullable().optional(),
    /** In-state; US only, and less than half of sticker_tuition at most publics. */
    tuition_in_state: z.number().min(0).nullable().optional(),
    /** null = unmeasured; [] = measured and awards none of these families. */
    programs: z.array(ProgramSchema).nullable().optional(),
    enrollment: z.number().int().min(0).nullable().optional(),
    size: z.enum(["small", "medium", "large"]),
    majors: z.array(z.string()).default([]),
    culture: CultureSchema,
    /** Curated per-school profile; null when none exists. Heterogeneous by section. */
    details: z.record(z.unknown()).nullable().optional(),
    provenance: z.record(ProvenanceSchema).default({}),
  })
  .strict();

export const AdmitTierSchema = z.enum(["extreme_reach", "reach", "target", "safety"]);

export const ResultSchema = z
  .object({
    university_id: z.string(),
    name: z.string(),
    score: z.number().min(0).max(1),
    rationale: z.string(),
    admit_tier: AdmitTierSchema.nullable().optional(),
    university: UniversitySummarySchema,
  })
  .strict();

export const TraceStepSchema = z
  .object({
    iteration: z.number().int().min(0),
    top_ids: z.array(z.string()),
    confidence: z.number().min(0).max(1),
    stop_reason: z.string().nullable(),
  })
  .strict();

export const StopReasonSchema = z.enum([
  "R1_converged",
  "R2_confident",
  "R3_no_change",
  "R4_iteration_cap",
]);

export const RecommendationResponseSchema = z
  .object({
    results: z.array(ResultSchema),
    confidence: z.number().min(0).max(1),
    stop_reason: StopReasonSchema,
    trace: z.array(TraceStepSchema),
  })
  .strict();

/** Full catalog record, as returned by GET /v1/universities for the browse view. */
export const UniversitySchema = z
  .object({
    id: z.string(),
    unitid: z.string().nullable().optional(),
    name: z.string(),
    country: z.string(),
    location: z.string(),
    region: RegionSchema,
    setting: SettingSchema,
    type: InstitutionTypeSchema,
    population: PopulationSchema.nullable().optional(),
    url: z.string().nullable().optional(),
    net_price_calculator_url: z.string().nullable().optional(),
    avg_gpa: z.number().min(0).max(4.0),
    avg_sat: z.number().int().nullable().optional(),
    acceptance_rate: z.number().min(0).max(1).nullable().optional(),
    net_price: z.number().min(0).nullable().optional(),
    sticker_tuition: z.number().min(0).nullable().optional(),
    tuition_in_state: z.number().min(0).nullable().optional(),
    programs: z.array(ProgramSchema).nullable().optional(),
    enrollment: z.number().int().nullable().optional(),
    size: z.enum(["small", "medium", "large"]),
    majors: z.array(z.string()).default([]),
    culture: CultureSchema,
    details: z.record(z.unknown()).nullable().optional(),
    provenance: z.record(ProvenanceSchema).default({}),
  })
  .strict();

export const CatalogResponseSchema = z
  .object({ universities: z.array(UniversitySchema) })
  .strict();

/** What was recognised in one free-text activity, so the UI can show the
 * student what the scorer will do with it before they submit. */
export const ClassifyRequestSchema = z
  .object({
    name: z.string().min(1),
    kind: z
      .enum(["competition", "club", "volunteering", "work", "sport", "arts", "research", "other"])
      .default("other"),
    description: z.string().max(500).nullable().optional(),
  })
  .strict();

export const ClassifyResponseSchema = z.object({ subjects: z.array(z.string()) }).strict();

export type University = z.infer<typeof UniversitySchema>;
export type CatalogResponse = z.infer<typeof CatalogResponseSchema>;

export type ClassifyRequest = z.infer<typeof ClassifyRequestSchema>;
export type ClassifyResponse = z.infer<typeof ClassifyResponseSchema>;

export type Profile = z.infer<typeof ProfileSchema>;
export type RecommendationRequest = z.infer<typeof RecommendationRequestSchema>;
export type RecommendationResponse = z.infer<typeof RecommendationResponseSchema>;
export type TraceStep = z.infer<typeof TraceStepSchema>;
export type Result = z.infer<typeof ResultSchema>;
export type UniversitySummary = z.infer<typeof UniversitySummarySchema>;
