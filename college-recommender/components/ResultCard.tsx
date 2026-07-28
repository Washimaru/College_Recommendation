import { formatStat, tierLabel, type StatKind } from "@/lib/format";
import type { Provenance, Result } from "@/lib/contract";

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

/** A whole card is the click target, so opening a profile needs no hunting
 *  for a small "details" link. */
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

  return (
    <button type="button" className="card" onClick={() => onOpen(result)}>
      <div className="card-head">
        <div>
          <h3>
            <span className="rank">{rank}</span>
            {result.name}
          </h3>
          <div className="loc">
            {uni.location} · {uni.country} · {uni.size}
          </div>
        </div>
        {tier && <span className={`tier ${result.admit_tier}`}>{tier}</span>}
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

      <div style={{ marginTop: 12, fontSize: 12.5, color: "var(--accent)", fontWeight: 650 }}>
        View full profile →
      </div>
    </button>
  );
}
