/**
 * Zod validators + TS types mirroring
 * docs/contracts/{profile,recommendation}.schema.json.
 *
 * This is one of the three contract mirrors (with the two schemas.py files).
 * Changing a shape here requires a version bump and matching edits on the
 * Python side — otherwise it is contract drift (H3).
 */
import { z } from "zod";

export const CONTRACT_VERSION = "2.0.0";

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

export const PreferencesSchema = z
  .object({
    max_tuition: z.number().min(0).nullable().optional(),
    preferred_size: z.enum(["small", "medium", "large"]).nullable().optional(),
    locations: z.array(z.string()).default([]),
  })
  .strict();

export const WeightsSchema = z
  .object({
    academic: z.number().min(0).optional(),
    cost: z.number().min(0).optional(),
    fit: z.number().min(0).optional(),
    culture: z.number().min(0).optional(),
  })
  .strict();

export const ProfileSchema = z
  .object({
    gpa: z.number().min(0).max(4.0),
    sat: z.number().int().min(400).max(1600).nullable().optional(),
    intended_major: z.string().min(1),
    culture_prefs: CulturePrefsSchema.optional(),
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

export const ResultSchema = z
  .object({
    university_id: z.string(),
    name: z.string(),
    score: z.number().min(0).max(1),
    rationale: z.string(),
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

export type Profile = z.infer<typeof ProfileSchema>;
export type RecommendationRequest = z.infer<typeof RecommendationRequestSchema>;
export type RecommendationResponse = z.infer<typeof RecommendationResponseSchema>;
export type TraceStep = z.infer<typeof TraceStepSchema>;
