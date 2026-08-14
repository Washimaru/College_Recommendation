/**
 * Which researchers work in which field of study.
 *
 * Two vocabularies meet here and neither was built for the other. A
 * researcher's `fields` are OpenAlex research fields — "Mathematics",
 * "Physics and Astronomy" — while a school's `programs` are the federal CIP
 * families it awards degrees in. This maps the first onto the second.
 *
 * The failure mode it avoids is a confident wrong answer: a field this map
 * does not know is never claimed for a family, so that researcher stays under
 * "All fields" rather than being filed under the nearest-looking major.
 *
 * (An earlier version mapped Wikidata occupations for the notable-faculty
 * list. That filter moved onto current researchers — a student choosing a
 * major wants someone they could take a class with — and the occupation map
 * went with it.)
 */
import type { Program } from "./contract";

/**
 * OpenAlex research field -> the CIP families a student would look for it
 * under. The active-faculty list speaks OpenAlex's vocabulary ("Physics and
 * Astronomy") where the notable list speaks Wikidata's ("physicist"), so the
 * two need separate maps even though they answer the same question.
 *
 * Mirrors `FIELD_TO_FAMILIES` in faculty-pipeline's active_faculty stage,
 * which uses it to reject implausible affiliations; here it drives the filter.
 */
export const FAMILIES_BY_RESEARCH_FIELD: Record<string, string[]> = {
  "Physics and Astronomy": ["Physical Sciences", "Engineering"],
  Chemistry: ["Physical Sciences", "Engineering"],
  "Earth and Planetary Sciences": ["Physical Sciences", "Natural Resources & Conservation"],
  "Environmental Science": ["Natural Resources & Conservation", "Physical Sciences"],
  Mathematics: ["Mathematics & Statistics", "Computer & Information Sciences"],
  "Computer Science": ["Computer & Information Sciences", "Engineering"],
  Engineering: ["Engineering", "Engineering Technologies", "Architecture"],
  "Materials Science": ["Engineering", "Physical Sciences"],
  "Chemical Engineering": ["Engineering"],
  Energy: ["Engineering", "Physical Sciences"],
  "Biochemistry, Genetics and Molecular Biology": ["Biological & Biomedical Sciences"],
  "Agricultural and Biological Sciences": [
    "Agriculture", "Biological & Biomedical Sciences", "Natural Resources & Conservation",
  ],
  "Immunology and Microbiology": ["Biological & Biomedical Sciences", "Health Professions"],
  Neuroscience: ["Biological & Biomedical Sciences", "Psychology", "Health Professions"],
  Medicine: ["Health Professions", "Biological & Biomedical Sciences"],
  Nursing: ["Health Professions"],
  Dentistry: ["Health Professions"],
  "Health Professions": ["Health Professions"],
  "Pharmacology, Toxicology and Pharmaceutics": [
    "Health Professions", "Biological & Biomedical Sciences",
  ],
  Psychology: ["Psychology", "Social Sciences"],
  "Social Sciences": [
    "Social Sciences", "Public Administration & Social Service",
    "Area, Ethnic & Gender Studies", "Education", "Legal Studies",
  ],
  "Economics, Econometrics and Finance": ["Social Sciences", "Business, Management & Marketing"],
  "Business, Management and Accounting": ["Business, Management & Marketing"],
  "Decision Sciences": ["Business, Management & Marketing", "Mathematics & Statistics"],
  "Arts and Humanities": [
    "Visual & Performing Arts", "English Language & Literature", "History",
    "Philosophy & Religious Studies", "Foreign Languages & Linguistics",
    "Liberal Arts & Humanities", "Communication & Journalism", "Architecture",
  ],
};

interface HasResearchFields {
  fields?: string[];
}

/** Researchers whose fields belong to `family`. Order preserved. */
export function researchersIn<T extends HasResearchFields>(
  researchers: T[],
  family: string,
): T[] {
  return researchers.filter((person) =>
    (person.fields ?? []).some((field) =>
      (FAMILIES_BY_RESEARCH_FIELD[field] ?? []).includes(family),
    ),
  );
}

/** Families the school awards degrees in and has an active researcher for. */
export function researchFamilies<T extends HasResearchFields>(
  researchers: T[] | null | undefined,
  programs: Program[] | null | undefined,
): string[] {
  if (!researchers || !programs) return [];
  return programs
    .map((program) => program.name)
    .filter((family) => researchersIn(researchers, family).length > 0);
}
