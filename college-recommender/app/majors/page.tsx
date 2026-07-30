"use client";

import { MajorFinder } from "@/components/MajorFinder";
import { useCatalog } from "@/lib/useCatalog";
import { useSchoolModal } from "@/lib/useSchoolModal";

export default function MajorsPage() {
  const { catalog, error } = useCatalog();
  const { open, modal } = useSchoolModal();

  return (
    <main className="wrap">
      <MajorFinder catalog={catalog} error={error} onOpen={open} />
      {modal}
    </main>
  );
}
