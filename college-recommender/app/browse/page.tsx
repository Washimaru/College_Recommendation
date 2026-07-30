"use client";

import { BrowseSection } from "@/components/BrowseSection";
import { useCatalog } from "@/lib/useCatalog";
import { useSchoolModal } from "@/lib/useSchoolModal";

export default function BrowsePage() {
  const { catalog, error } = useCatalog();
  const { open, modal } = useSchoolModal();

  return (
    <main className="wrap">
      <BrowseSection catalog={catalog} error={error} onOpen={open} />
      {modal}
    </main>
  );
}
