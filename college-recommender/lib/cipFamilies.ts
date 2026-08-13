/**
 * Major Finder majors → the federal CIP family that measures them.
 *
 * Two taxonomies, so this is a mapping and not a claim: the Major Finder's
 * fields are how a student describes an interest, while `University.programs`
 * counts degrees actually awarded under the 2-digit CIP families Scorecard
 * publishes. One is coarser than the other — Mechanical, Electrical and
 * Biomedical Engineering all land in "Engineering" — which is why the UI says
 * "awards degrees in this area" rather than naming the exact programme.
 *
 * A major with no entry here simply makes no federal claim. That is the point:
 * `majors` (editorial strengths) can never support "this school does not offer
 * X", and a guessed mapping would not either.
 */
export const MAJOR_TO_CIP_FAMILY: Record<string, string> = {
  "Computer Science": "Computer & Information Sciences",
  "Data Science / Statistics": "Mathematics & Statistics",
  "Mechanical / General Engineering": "Engineering",
  "Electrical & Computer Engineering": "Engineering",
  "Biomedical Engineering": "Engineering",
  Biology: "Biological & Biomedical Sciences",
  Chemistry: "Physical Sciences",
  Physics: "Physical Sciences",
  Mathematics: "Mathematics & Statistics",
  Neuroscience: "Biological & Biomedical Sciences",
  Nursing: "Health Professions",
  "Public Health": "Health Professions",
  Psychology: "Psychology",
  Economics: "Social Sciences",
  "Business / Management": "Business, Management & Marketing",
  "Finance / Accounting": "Business, Management & Marketing",
  "Marketing / Communications": "Business, Management & Marketing",
  "Political Science": "Social Sciences",
  "International Relations": "Social Sciences",
  "English / Literature": "English Language & Literature",
  History: "History",
  Philosophy: "Philosophy & Religious Studies",
  "Sociology / Social Work": "Social Sciences",
  Education: "Education",
  "Art & Design": "Visual & Performing Arts",
  Music: "Visual & Performing Arts",
  "Film / Theatre": "Visual & Performing Arts",
  Architecture: "Architecture",
  "Environmental Science": "Natural Resources & Conservation",
};

interface HasPrograms {
  programs?: { name: string; share: number }[] | null;
}

/** Does this school award degrees in `family`? `null` when nobody measured it,
 *  which is not the same as "no" and must not be rendered as one. */
export function awardsDegreesIn(school: HasPrograms, family: string): boolean | null {
  if (school.programs === null || school.programs === undefined) return null;
  return school.programs.some((program) => program.name === family);
}

export interface FamilyCoverage {
  family: string;
  awarding: number;
  none: number;
  unmeasured: number;
}

/**
 * How many schools in the catalog award degrees in a family, how many award
 * none, and how many were never measured.
 *
 * The middle number is the one the editorial `majors` list could never
 * produce, and the third is why it is reported separately rather than folded
 * into it — every non-US school is unmeasured, and counting those as "awards
 * none" would be exactly the false claim this data exists to prevent.
 */
export function familyCoverage(schools: HasPrograms[], family: string): FamilyCoverage {
  let awarding = 0;
  let none = 0;
  let unmeasured = 0;
  for (const school of schools) {
    const answer = awardsDegreesIn(school, family);
    if (answer === null) unmeasured += 1;
    else if (answer) awarding += 1;
    else none += 1;
  }
  return { family, awarding, none, unmeasured };
}
