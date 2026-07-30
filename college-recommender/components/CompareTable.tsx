import { AXIS_LABELS, CULTURE_AXES } from "@/lib/contract";
import { formatStat, tierLabel, type StatKind } from "@/lib/format";
import type { ListedSchool } from "@/lib/profileStore";

const ROWS: { label: string; key: string; kind: StatKind }[] = [
  { label: "Avg GPA", key: "avg_gpa", kind: "decimal" },
  { label: "Avg SAT", key: "avg_sat", kind: "score" },
  { label: "Acceptance", key: "acceptance_rate", kind: "percent" },
  { label: "Net price", key: "net_price", kind: "money" },
  { label: "Undergrads", key: "enrollment", kind: "number" },
];

export function CompareTable({ schools }: { schools: ListedSchool[] }) {
  if (schools.length === 0) return null;

  return (
    <div style={{ overflowX: "auto" }}>
      <table className="cmp">
        <thead>
          <tr>
            <th />
            {schools.map((s) => (
              <th key={s.id}>
                {s.name}
                <div className="loc">
                  {s.university.location} · {s.university.country}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            <th>Fit</th>
            {schools.map((s) => (
              <td key={s.id}>
                <b>{s.fit === null ? "—" : `${Math.round(s.fit * 100)}%`}</b>
              </td>
            ))}
          </tr>
          <tr>
            <th>Tier</th>
            {schools.map((s) => (
              <td key={s.id}>
                {tierLabel(s.tier) ? (
                  <span className={`tier ${s.tier}`}>{tierLabel(s.tier)}</span>
                ) : (
                  "—"
                )}
              </td>
            ))}
          </tr>

          {ROWS.map((row) => (
            <tr key={row.key}>
              <th>{row.label}</th>
              {schools.map((s) => {
                const uni = s.university as unknown as Record<string, number | null | undefined>;
                const rendered = formatStat(
                  uni[row.key],
                  s.university.provenance[row.key],
                  row.kind,
                );
                return (
                  <td key={s.id} title={rendered.note ?? undefined}>
                    {rendered.text}
                    {rendered.note && <span className="note"> {rendered.note}</span>}
                  </td>
                );
              })}
            </tr>
          ))}

          <tr>
            <th>International share</th>
            {schools.map((s) => {
              // Provenance lives at the `population` object level, not per
              // field inside it: absent for 90 non-US schools where the stat
              // does not apply, present (with international_share possibly
              // still null) for the rest. Reading a missing population as 0%
              // would misreport a school as having no international students.
              const rendered = formatStat(
                s.university.population?.international_share,
                s.university.provenance.population,
                "percent",
              );
              return (
                <td key={s.id} title={rendered.note ?? undefined}>
                  {rendered.text}
                  {rendered.note && <span className="note"> {rendered.note}</span>}
                </td>
              );
            })}
          </tr>

          <tr>
            <th>Setting</th>
            {schools.map((s) => (
              <td key={s.id}>
                {s.university.setting} · {s.university.type}
              </td>
            ))}
          </tr>

          {CULTURE_AXES.map((axis) => (
            <tr key={axis}>
              <th style={{ fontWeight: 500, fontSize: 12 }}>{AXIS_LABELS[axis].right}</th>
              {schools.map((s) => (
                <td key={s.id}>
                  <div className="fit-bar" style={{ maxWidth: 120 }}>
                    <span style={{ width: `${s.university.culture[axis] * 100}%` }} />
                  </div>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
