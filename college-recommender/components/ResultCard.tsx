import { formatStat, tierLabel, type StatKind } from "@/lib/format";
import type { Provenance, Result } from "@/lib/contract";
import { COMPARE_LIMIT, useProfileStore } from "@/lib/profileStore";

function Stat({
  label,
  value,
  provenance,
  kind,
}: {
  label: string;
  value: number | null | undefined;
  provenance: Provenance | undefined;
  kind: StatKind;
}) {
  const { text, note } = formatStat(value, provenance, kind);
  return (
    <div>
      <dt>{label}</dt>
      <dd title={note ?? undefined}>
        {text}
        {note && <span className="note">{note}</span>}
      </dd>
    </div>
  );
}

/**
 * A card with several interactive controls (view profile, add to list, add
 * to compare) can't itself be a <button> — a <button> inside a <button> is
 * invalid HTML and breaks keyboard/screen-reader behaviour. The click target
 * for opening a profile is the dedicated "View full profile" control below.
 */
export function ResultCard({
  result,
  rank,
  onOpen,
}: {
  result: Result;
  rank: number;
  onOpen: (result: Result) => void;
}) {
  const uni = result.university;
  const tier = tierLabel(result.admit_tier);
  const fit = Math.round(result.score * 100);

  const { addToList, isListed, addToCompare, compare } = useProfileStore();
  const listed = isListed(result.university_id);
  const compareFull = compare.length >= COMPARE_LIMIT;
  const inCompare = compare.some((s) => s.id === result.university_id);
  const asListed = {
    id: result.university_id,
    name: result.name,
    fit: result.score,
    tier: result.admit_tier ?? null,
    university: result.university,
  };

  return (
    <div className="card" role="group" aria-label={result.name}>
      <div className="card-head">
        <div style={{ minWidth: 0 }}>
          <h3>
            <span className="rank">{rank}</span>
            {result.name}
          </h3>
          <div className="loc">
            {uni.location} · {uni.country} · {uni.size}
          </div>
        </div>

        <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
          {tier && <span className={`tier ${result.admit_tier}`}>{tier}</span>}
          <div className="fit">
            <b>{fit}%</b>
            <span>fit</span>
            <div className="fit-bar">
              <span style={{ width: `${fit}%` }} />
            </div>
          </div>
        </div>
      </div>

      <p style={{ margin: "10px 0 0", fontSize: 14 }}>{result.rationale}</p>

      <dl className="stats">
        <Stat label="Avg GPA" value={uni.avg_gpa} provenance={uni.provenance.avg_gpa} kind="decimal" />
        <Stat label="Avg SAT" value={uni.avg_sat} provenance={uni.provenance.avg_sat} kind="score" />
        <Stat
          label="Acceptance"
          value={uni.acceptance_rate}
          provenance={uni.provenance.acceptance_rate}
          kind="percent"
        />
        <Stat
          label="Net price"
          value={uni.net_price}
          provenance={uni.provenance.net_price}
          kind="money"
        />
      </dl>

      <div style={{ display: "flex", gap: 8, marginTop: 14, flexWrap: "wrap" }}>
        <button type="button" className="chip" onClick={() => onOpen(result)}>
          View full profile →
        </button>
        <button
          type="button"
          className={`chip ${listed ? "on" : ""}`}
          disabled={listed}
          onClick={() => addToList(asListed)}
        >
          {listed ? "On your list" : "Add to my list"}
        </button>
        <button
          type="button"
          className={`chip ${inCompare ? "on" : ""}`}
          disabled={inCompare || compareFull}
          title={compareFull && !inCompare ? "Compare is full — remove one to add another" : undefined}
          onClick={() => addToCompare(asListed)}
        >
          {inCompare ? "Comparing" : compareFull ? "Compare full" : "Compare"}
        </button>
      </div>
    </div>
  );
}
