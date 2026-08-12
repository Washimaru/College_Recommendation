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

const PROVENANCE_LABELS: Partial<Record<Provenance, string>> = {
  web_verified: "researched from published sources",
  editorial: "estimated",
};

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

  // Only the two provenances that were actually earned carry a claim. Anything
  // else - "absent", "not_applicable", or a value this build has never seen -
  // says nothing at all, rather than falling through to the strongest label on
  // offer and telling a student an unsourced profile was verified.
  const label = PROVENANCE_LABELS[provenance ?? "absent"] ?? null;

  const { scholarships, research, outcomes, gradSchools, proSchools, programs, faculty, src } =
    details;
  const facultyEntries = asList(faculty);
  // The data itself sometimes already ends with a caveat like
  // "(Faculty change — verify.)" - only add the general one when none of the
  // entries already carries it, so we never say it twice.
  const facultyAlreadyCaveated = facultyEntries.some((entry) => /verify/i.test(entry));

  return (
    <>
      <p
        className="muted"
        style={{ fontSize: 11.5, marginTop: 24, textTransform: "uppercase", letterSpacing: 0.5 }}
      >
        School profile{label ? ` · ${label}` : ""}
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

      {facultyEntries.length > 0 && (
        <Section title="Notable faculty">
          {facultyEntries.map((item) => (
            <p key={item} style={{ margin: "6px 0" }}>
              {item}
            </p>
          ))}
          {!facultyAlreadyCaveated && (
            <p className="muted" style={{ margin: "6px 0 0", fontSize: 12 }}>
              Faculty move, retire and change roles — verify current affiliation before relying
              on this.
            </p>
          )}
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
