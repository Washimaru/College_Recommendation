"use client";

import { useState } from "react";

import { ResultCard } from "@/components/ResultCard";
import type { RecommendationResponse, Result } from "@/lib/contract";
import { useSchoolModal } from "@/lib/useSchoolModal";

const PAGE = 10;
type Sort = "match" | "price" | "selectivity";

const SORTS: [Sort, string][] = [
  ["match", "Best match"],
  ["price", "Lowest price"],
  ["selectivity", "Most selective"],
];

export function MatchResults({ response }: { response: RecommendationResponse }) {
  const [sort, setSort] = useState<Sort>("match");
  const [tiers, setTiers] = useState<string[]>([]);
  const [shown, setShown] = useState(PAGE);
  const { open, modal } = useSchoolModal();

  const all = response.results;
  const filtered = tiers.length
    ? all.filter((r) => r.admit_tier && tiers.includes(r.admit_tier))
    : all;
  const results = [...filtered].sort((a, b) => {
    if (sort === "price") return (a.university.net_price ?? 1e9) - (b.university.net_price ?? 1e9);
    if (sort === "selectivity")
      return (a.university.acceptance_rate ?? 1) - (b.university.acceptance_rate ?? 1);
    return b.score - a.score;
  });

  const toggleTier = (tier: string) => {
    setTiers((current) =>
      current.includes(tier) ? current.filter((t) => t !== tier) : [...current, tier],
    );
    setShown(PAGE);
  };

  if (all.length === 0) {
    return (
      <p className="notice empty" style={{ marginTop: 22 }}>
        No schools matched. Try raising your maximum net price, widening the country or
        institution-type filter, or choosing a different major.
      </p>
    );
  }

  return (
    <section className="section" id="results">
      <h2>Your matches</h2>
      <p className="muted" style={{ fontSize: 14, margin: "0 0 18px" }}>
        Showing {Math.min(shown, results.length)} of {results.length}
        {tiers.length > 0 && <> (filtered from {all.length})</>} · click a school for its full
        profile
      </p>

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: 18 }}>
        <span className="muted" style={{ fontSize: 13 }}>Sort</span>
        {SORTS.map(([key, label]) => (
          <button
            key={key} type="button" className={`chip ${sort === key ? "on" : ""}`}
            onClick={() => setSort(key)}
          >
            {label}
          </button>
        ))}
        <span className="muted" style={{ fontSize: 13, marginLeft: 10 }}>Filter</span>
        {["reach", "target", "safety"].map((tier) => (
          <button
            key={tier} type="button" className={`chip ${tiers.includes(tier) ? "on" : ""}`}
            onClick={() => toggleTier(tier)}
          >
            {tier[0].toUpperCase() + tier.slice(1)}
          </button>
        ))}
      </div>

      <div className="cards">
        {results.slice(0, shown).map((result: Result, index) => (
          <ResultCard key={result.university_id} result={result} rank={index + 1} onOpen={open} />
        ))}
      </div>

      {results.length > shown && (
        <div style={{ textAlign: "center", marginTop: 20 }}>
          <button type="button" className="btn ghost" onClick={() => setShown(shown + PAGE)}>
            Show more schools ({results.length - shown} left)
          </button>
        </div>
      )}

      {modal}
    </section>
  );
}
