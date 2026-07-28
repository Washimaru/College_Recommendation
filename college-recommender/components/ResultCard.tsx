import { formatStat, tierLabel, type StatKind } from "@/lib/format";
import type { Provenance, Result } from "@/lib/contract";

const TIER_STYLES: Record<string, string> = {
  Reach: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200",
  Target: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
  Safety: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-200",
};

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
  const rendered = formatStat(value, provenance, kind);
  return (
    <div>
      <dt className="text-xs text-neutral-500 dark:text-neutral-400">{label}</dt>
      <dd className="text-sm font-medium" title={rendered.note ?? undefined}>
        {rendered.text}
        {rendered.note && (
          <span className="ml-1 text-xs font-normal text-neutral-500">
            {rendered.note}
          </span>
        )}
      </dd>
    </div>
  );
}

export function ResultCard({ result, rank }: { result: Result; rank: number }) {
  const uni = result.university;
  const tier = tierLabel(result.admit_tier);

  return (
    <li className="rounded-lg border border-neutral-200 p-4 dark:border-neutral-800">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold">
            <span className="mr-2 text-neutral-400">{rank}.</span>
            {result.name}
          </h3>
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            {uni.location} · {uni.country} · {uni.size}
          </p>
        </div>
        {tier && (
          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${TIER_STYLES[tier]}`}
          >
            {tier}
          </span>
        )}
      </div>

      <p className="mt-2 text-sm">{result.rationale}</p>

      <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
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
    </li>
  );
}
