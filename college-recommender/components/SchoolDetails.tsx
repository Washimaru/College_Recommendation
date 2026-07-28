import type { Provenance, SchoolDetails as Details } from "@/lib/contract";

/** Sections render only when the school actually has them. Coverage is sparse
 *  and uneven by design - nothing here is generated to fill a gap. */
function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <>
      <h3 style={{ marginTop: 22, fontSize: 14, letterSpacing: 0.3 }}>{title}</h3>
      <div style={{ fontSize: 13.5 }}>{children}</div>
    </>
  );
}

function asList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String);
  if (typeof value === "string") return [value];
  return [];
}

export function SchoolDetailSections({
  details,
  provenance,
}: {
  details: Details | null | undefined;
  provenance: Provenance | undefined;
}) {
  if (!details) return null;

  const label =
    provenance === "web_verified"
      ? "researched from published sources"
      : provenance === "editorial"
        ? "estimated"
        : "verified profile";

  const { scholarships, research, outcomes, gradSchools, proSchools, programs, src } = details;

  return (
    <>
      <p
        className="muted"
        style={{ fontSize: 11.5, marginTop: 24, textTransform: "uppercase", letterSpacing: 0.5 }}
      >
        School profile · {label}
      </p>

      {scholarships && (
        <Section title="Scholarships & aid">
          {scholarships.policy && <p style={{ margin: "6px 0" }}>{scholarships.policy}</p>}
          {scholarships.named && scholarships.named.length > 0 && (
            <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
              {scholarships.named.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}
        </Section>
      )}

      {research && (
        <Section title="Research">
          {research.level && (
            <p style={{ margin: "6px 0" }}>
              <b>Level:</b> {research.level}
            </p>
          )}
          {research.undergrad && (
            <p style={{ margin: "6px 0" }}>
              <b>For undergraduates:</b> {research.undergrad}
            </p>
          )}
          {research.areas && <p style={{ margin: "6px 0" }}>{research.areas}</p>}
        </Section>
      )}

      {(gradSchools || proSchools) && (
        <Section title="Graduate & professional schools">
          {asList(gradSchools).map((item) => (
            <p key={item} style={{ margin: "6px 0" }}>
              {item}
            </p>
          ))}
          {asList(proSchools).map((item) => (
            <p key={item} style={{ margin: "6px 0" }}>
              {item}
            </p>
          ))}
        </Section>
      )}

      {outcomes && (
        <Section title="After graduation">
          {outcomes.gradRate && (
            <p style={{ margin: "6px 0" }}>
              <b>Graduation rate:</b> {outcomes.gradRate}
            </p>
          )}
          {outcomes.salary && (
            <p style={{ margin: "6px 0" }}>
              <b>Early-career salary:</b> {outcomes.salary}
            </p>
          )}
          {outcomes.paths && <p style={{ margin: "6px 0" }}>{outcomes.paths}</p>}
          {outcomes.employers && outcomes.employers.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
              {outcomes.employers.map((employer) => (
                <span key={employer} className="chip">
                  {employer}
                </span>
              ))}
            </div>
          )}
        </Section>
      )}

      {programs && (
        <Section title="Notable programs">
          {asList(programs).map((item) => (
            <p key={item} style={{ margin: "6px 0" }}>
              {item}
            </p>
          ))}
        </Section>
      )}

      {src && src.length > 0 && (
        <p className="muted" style={{ fontSize: 11.5, marginTop: 16 }}>
          Sources: {src.join(" · ")}
        </p>
      )}
    </>
  );
}
