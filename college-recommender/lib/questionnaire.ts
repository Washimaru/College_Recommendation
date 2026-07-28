/**
 * Personality questionnaire.
 *
 * Every question asks directly about a *preference* — what the student wants
 * from a campus — and the answer is used as self-report. It never infers campus
 * fit from a personality type, which is the part that was unfounded and got
 * MBTI removed from the model.
 *
 * Answers drive two separate things, deliberately non-overlapping:
 *   `culture`     one of the six bipolar culture axes
 *   `personality` intensity or scale, scored against selectivity/enrollment
 */
import { CENTRED_PREFS, type CulturePrefs, type Personality } from "./contract";

export type Target =
  | { kind: "culture"; axis: keyof CulturePrefs }
  | { kind: "personality"; axis: keyof Personality };

export interface Question {
  id: string;
  prompt: string;
  /** Choosing this end sends the target toward 0.0 … */
  low: string;
  /** … and this end toward 1.0. */
  high: string;
  target: Target;
}

export const QUESTIONS: Question[] = [
  {
    id: "collab",
    prompt: "Your class is graded on a curve. How does that sit with you?",
    low: "Fine — I do my best work competing",
    high: "Badly — I'd rather we all helped each other",
    target: { kind: "culture", axis: "collab" },
  },
  {
    id: "quirky",
    prompt: "It's Friday night on campus. What sounds better?",
    low: "A big party with everyone there",
    high: "An odd little club arguing about something niche",
    target: { kind: "culture", axis: "quirky" },
  },
  {
    id: "idealist",
    prompt: "You're picking between two job offers. What decides it?",
    low: "The one that pays and promotes faster",
    high: "The one doing work I believe in",
    target: { kind: "culture", axis: "idealist" },
  },
  {
    id: "research",
    prompt: "A subject finally clicks for you when…",
    low: "I build something real with it",
    high: "I understand the theory underneath it",
    target: { kind: "culture", axis: "research" },
  },
  {
    id: "spirit",
    prompt: "Your school reaches a national championship final.",
    low: "I'd barely notice",
    high: "I'd be painted head to toe",
    target: { kind: "culture", axis: "spirit" },
  },
  {
    id: "seminar",
    prompt: "Which class would you learn more in?",
    low: "A 300-person lecture I can disappear into",
    high: "A 12-person seminar where I have to talk",
    target: { kind: "culture", axis: "seminar" },
  },
  {
    id: "intensity",
    prompt: "Be honest about workload.",
    low: "I want room to breathe and explore",
    high: "Push me hard — I want to be surrounded by intense people",
    target: { kind: "personality", axis: "intensity" },
  },
  {
    id: "scale",
    prompt: "Two months in, what would feel right?",
    low: "Knowing most faces on campus",
    high: "Still discovering new corners and new people",
    target: { kind: "personality", axis: "scale" },
  },
];

/** 5-point scale; the midpoint is a genuine "no preference". */
export const CHOICES = [0, 0.25, 0.5, 0.75, 1] as const;

export interface QuestionnaireResult {
  culturePrefs: CulturePrefs;
  personality: Personality;
  /** How many questions were actually answered. */
  answered: number;
}

/**
 * Fold answers into the two vectors. Unanswered questions stay at 0.5, which
 * every scorer treats as "no preference expressed" and weights at zero.
 */
export function foldAnswers(answers: Record<string, number>): QuestionnaireResult {
  const culturePrefs: CulturePrefs = { ...CENTRED_PREFS };
  const personality: Personality = { intensity: 0.5, scale: 0.5 };
  let answered = 0;

  for (const question of QUESTIONS) {
    const value = answers[question.id];
    if (value === undefined) continue;
    answered += 1;
    if (question.target.kind === "culture") {
      culturePrefs[question.target.axis] = value;
    } else {
      personality[question.target.axis] = value;
    }
  }

  return { culturePrefs, personality, answered };
}
