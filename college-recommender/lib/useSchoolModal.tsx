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

/** One modal implementation shared by every route. */
export function useSchoolModal(): {
  open: (school: { name: string; university?: UniversitySummary } & Partial<Opened>) => void;
  modal: ReactNode;
} {
  const [opened, setOpened] = useState<Opened | null>(null);

  const open = (school: { name: string; university?: UniversitySummary } & Partial<Opened>) =>
    setOpened({
      name: school.name,
      university: (school.university ?? school) as UniversitySummary,
      rationale: school.rationale,
      admitTier: school.admitTier,
    });

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
