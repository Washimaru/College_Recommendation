"use client";

import { useState, type ReactNode } from "react";

import { UniversityModal } from "@/components/UniversityModal";
import type { AdmitTier, UniversitySummary } from "./contract";

interface Opened {
  name: string;
  university: UniversitySummary;
  rationale?: string;
  admitTier?: AdmitTier | null;
}

/**
 * What `open` accepts — two genuinely different shapes, so it is a union rather
 * than one loose object type:
 *
 *   `Nested`  a `Result` from Match, which holds its school under `.university`
 *             and names the tier `admit_tier`, the contract's snake_case.
 *   `Flat`    a whole `University` from Browse or Major Finder, which extends
 *             `UniversitySummary` and so serves as its own school, with no tier.
 *
 * Reading only `admitTier` silently dropped the Reach/Target/Safety badge from
 * every modal opened off a match card, while the card behind it kept one — hence
 * both spellings are accepted.
 */
type Nested = {
  name: string;
  university: UniversitySummary;
  rationale?: string;
  admitTier?: AdmitTier | null;
  admit_tier?: AdmitTier | null;
};
type Flat = UniversitySummary & { name: string };
export type Openable = Nested | Flat;

/** One modal implementation shared by every route. */
export function useSchoolModal(): {
  open: (school: Openable) => void;
  modal: ReactNode;
} {
  const [opened, setOpened] = useState<Opened | null>(null);

  const open = (school: Openable) =>
    setOpened(
      "university" in school
        ? {
            name: school.name,
            university: school.university,
            rationale: school.rationale,
            admitTier: school.admitTier ?? school.admit_tier ?? null,
          }
        : { name: school.name, university: school, admitTier: null },
    );

  return {
    open,
    modal: opened ? (
      <UniversityModal
        name={opened.name}
        university={opened.university}
        rationale={opened.rationale}
        admitTier={opened.admitTier}
        onClose={() => setOpened(null)}
      />
    ) : null,
  };
}
