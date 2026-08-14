/**
 * Which professors work in which field of study.
 *
 * Two vocabularies meet here and neither was built for the other. A
 * professor's `fields` are Wikidata occupations — "physicist", "economist",
 * "composer" — while a school's `programs` are the federal CIP families it
 * awards degrees in — "Physical Sciences", "Business, Management & Marketing".
 * This maps the first onto the second.
 *
 * The failure mode it is built to avoid is a confident wrong answer. An
 * occupation this map does not know is simply not claimed for any family: the
 * professor still appears under "All fields", and no field asserts them. That
 * is why the map is an allowlist of occupations rather than a set of rules
 * with a fallback bucket.
 */
import type { NotableProfessor, Program } from "./contract";

/** CIP family -> the occupations that belong to it. */
export const OCCUPATIONS_BY_FAMILY: Record<string, string[]> = {
  "Computer & Information Sciences": [
    "computer scientist", "programmer", "software engineer", "software developer",
    "computer programmer", "roboticist", "cryptographer",
  ],
  Engineering: [
    "engineer", "civil engineer", "electrical engineer", "mechanical engineer",
    "aerospace engineer", "chemical engineer", "inventor", "nuclear engineer",
  ],
  "Mathematics & Statistics": ["mathematician", "statistician", "logician"],
  "Physical Sciences": [
    "physicist", "chemist", "astronomer", "astrophysicist", "geologist",
    "theoretical physicist", "nuclear physicist", "crystallographer", "meteorologist",
  ],
  "Biological & Biomedical Sciences": [
    "biologist", "biochemist", "geneticist", "neuroscientist", "microbiologist",
    "zoologist", "botanist", "ecologist", "molecular biologist", "physiologist",
  ],
  "Health Professions": [
    "physician", "nurse", "surgeon", "psychiatrist", "epidemiologist", "dentist",
    "pharmacologist", "public health specialist", "veterinarian",
  ],
  Psychology: ["psychologist", "psychoanalyst", "psychotherapist"],
  "Social Sciences": [
    "economist", "sociologist", "anthropologist", "political scientist",
    "geographer", "archaeologist", "criminologist", "demographer",
  ],
  "Business, Management & Marketing": [
    "businessperson", "entrepreneur", "management consultant", "accountant",
    "business executive", "marketing executive",
  ],
  "Legal Studies": ["lawyer", "jurist", "judge", "legal scholar", "attorney"],
  "English Language & Literature": [
    "writer", "poet", "novelist", "literary critic", "essayist", "playwright",
    "literary scholar", "short story writer", "author",
  ],
  History: ["historian", "historian of science", "art historian", "medievalist"],
  "Philosophy & Religious Studies": [
    "philosopher", "theologian", "ethicist", "biblical scholar", "logician",
  ],
  "Foreign Languages & Linguistics": [
    "linguist", "translator", "philologist", "lexicographer",
  ],
  "Visual & Performing Arts": [
    "composer", "musician", "painter", "sculptor", "photographer", "actor",
    "film director", "dancer", "choreographer", "artist", "conductor",
    "graphic designer", "illustrator", "singer", "pianist", "designer",
    "music educator", "screenwriter", "cinematographer",
  ],
  Architecture: ["architect", "landscape architect", "urban planner"],
  Education: ["educator", "pedagogue", "education theorist"],
  "Communication & Journalism": [
    "journalist", "broadcaster", "news presenter", "media scholar", "editor",
  ],
  "Natural Resources & Conservation": [
    "environmentalist", "conservationist", "forester", "climatologist",
  ],
  "Agriculture": ["agronomist", "agricultural scientist", "horticulturist"],
  "Area, Ethnic & Gender Studies": ["africanist", "sinologist", "feminist theorist"],
  "Public Administration & Social Service": ["social worker", "civil servant", "diplomat"],
  "Parks, Recreation & Fitness": ["coach", "sports coach", "athlete"],
};

function haystack(person: NotableProfessor): string {
  return [...(person.fields ?? []), person.known_for ?? ""].join(" · ").toLowerCase();
}

/**
 * Professors who work in `family`.
 *
 * Matches occupations first and falls back to the one-line description, which
 * is how someone with no occupation statement — "American mathematician and
 * logician" — still reaches the right field. Order is preserved, so the most
 * widely known still lead.
 */
export function professorsIn(
  faculty: NotableProfessor[],
  family: string,
): NotableProfessor[] {
  const occupations = OCCUPATIONS_BY_FAMILY[family];
  if (!occupations) return [];
  return faculty.filter((person) => {
    const text = haystack(person);
    return occupations.some((occupation) => text.includes(occupation));
  });
}

/**
 * The families worth offering as a filter for one school: those it awards
 * degrees in *and* has at least one professor for.
 *
 * Both halves matter. Offering a family the school does not teach would
 * invent a programme; offering one with nobody behind it would send a student
 * to an empty list and imply the school has no faculty there, when all it
 * means is that nobody in it has a Wikipedia article.
 */
export function familiesWithProfessors(
  faculty: NotableProfessor[],
  programs: Program[] | null | undefined,
): string[] {
  if (!programs) return [];
  return programs
    .map((program) => program.name)
    .filter((family) => professorsIn(faculty, family).length > 0);
}
