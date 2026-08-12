"use client";

import { AXIS_LABELS, CULTURE_AXES, type AdmitTier, type UniversitySummary } from "@/lib/contract";
import { formatStat, tierLabel, type StatKind } from "@/lib/format";
import { useFocusTrap } from "@/lib/useFocusTrap";
import { SchoolDetailSections } from "./SchoolDetails";

function Stat({
  label,
  value,
  provenance,
  kind,
}: {
  label: string;
  value: number | null | undefined;
  provenance: Parameters<typeof formatStat>[1];
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
 * Full profile for one school. Everything shown comes from the catalog, so a
 * figure is either observed, an editorial estimate, or explicitly absent -
 * there is no filler.
 */
export function UniversityModal({
  name,
  university,
  rationale,
  admitTier,
  onClose,
}: {
  name: string;
  university: UniversitySummary;
  /** Present when opened from a match; absent when opened from browse. */
  rationale?: string;
  admitTier?: AdmitTier | null;
  onClose: () => void;
}) {
  // Owns Escape as well as the trap, so both modals close identically.
  const dialogRef = useFocusTrap<HTMLDivElement>(onClose);

  const uni = university;
  const tier = tierLabel(admitTier);
  const sameTuition =
    uni.tuition_in_state != null &&
    uni.sticker_tuition != null &&
    uni.tuition_in_state === uni.sticker_tuition;

  return (
    <div
      className="modal-back"
      role="dialog"
      aria-modal="true"
      aria-label={name}
      onClick={onClose}
    >
      <div className="modal" ref={dialogRef} onClick={(event) => event.stopPropagation()}>
        <div className="card-head">
          <div>
            <h2 style={{ marginBottom: 2 }}>{name}</h2>
            <p className="loc muted">
              {uni.location} · {uni.country} · {uni.size} campus
            </p>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {tier && <span className={`tier ${admitTier}`}>{tier}</span>}
            <button className="icon-btn" onClick={onClose} aria-label="Close">
              ✕
            </button>
          </div>
        </div>

        {rationale && <p style={{ marginTop: 14 }}>{rationale}</p>}

        <h3 style={{ marginTop: 22, fontSize: 14, letterSpacing: 0.3 }}>Admissions & cost</h3>
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
          <Stat
            label="Undergrads"
            value={uni.enrollment}
            provenance={uni.provenance.enrollment}
            kind="number"
          />
          {/*
            Two prices only where there genuinely are two. Every private school
            in the catalog reports the same figure for both, so showing an
            "in state" row there would invent a distinction the school does not
            make — while showing only the out-of-state price at a public one
            overstates the cost to a resident by tens of thousands.
          */}
          {sameTuition ? (
            <Stat
              label="Tuition"
              value={uni.sticker_tuition}
              provenance={uni.provenance.sticker_tuition}
              kind="money"
            />
          ) : (
            <>
              {uni.tuition_in_state != null && (
                <Stat
                  label="Tuition (in state)"
                  value={uni.tuition_in_state}
                  provenance={uni.provenance.tuition_in_state}
                  kind="money"
                />
              )}
              <Stat
                label={
                  uni.tuition_in_state != null ? "Tuition (out of state)" : "Tuition"
                }
                value={uni.sticker_tuition}
                provenance={uni.provenance.sticker_tuition}
                kind="money"
              />
            </>
          )}
        </dl>

        {uni.programs !== null && uni.programs !== undefined && (
          <>
            <h3 style={{ marginTop: 24, fontSize: 14, letterSpacing: 0.3 }}>
              Degrees awarded
            </h3>
            <p className="muted" style={{ fontSize: 12.5, margin: "0 0 12px" }}>
              Federal data on the degrees this school actually awards, by share.
              Unlike the strengths listed above, this is complete — so a field
              that is missing here is one the school does not award degrees in.
            </p>
            {uni.programs.length === 0 ? (
              <p style={{ fontSize: 13.5, margin: 0 }}>
                This school awards no degrees in any of the fields the federal
                data covers.
              </p>
            ) : (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {uni.programs.slice(0, 12).map((program) => (
                  <span key={program.name} className="chip">
                    {program.name} · {Math.round(program.share * 100)}%
                  </span>
                ))}
              </div>
            )}
          </>
        )}

        <h3 style={{ marginTop: 24, fontSize: 14, letterSpacing: 0.3 }}>Campus culture</h3>
        <p className="muted" style={{ fontSize: 12.5, margin: "0 0 12px" }}>
          Editorial estimates of how the campus feels, on the same six axes you set.
        </p>
        <div className="vibe">
          {CULTURE_AXES.map((axis) => (
            <div key={axis} className="vibe-row">
              <div>
                <div className="vibe-track">
                  <div
                    className="vibe-fill"
                    style={{ width: `${uni.culture[axis] * 100}%` }}
                  />
                </div>
                <div className="slider-ends">
                  <span>{AXIS_LABELS[axis].left}</span>
                  <span>{AXIS_LABELS[axis].right}</span>
                </div>
              </div>
              <span className="vibe-label">
                {Math.round(uni.culture[axis] * 100)}% toward {AXIS_LABELS[axis].right.toLowerCase()}
              </span>
            </div>
          ))}
        </div>

        {uni.majors.length > 0 && (
          <>
            <h3 style={{ marginTop: 24, fontSize: 14, letterSpacing: 0.3 }}>Known for</h3>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {uni.majors.map((major) => (
                <span key={major} className="chip">
                  {major}
                </span>
              ))}
            </div>
          </>
        )}

        <SchoolDetailSections
          details={uni.details}
          provenance={uni.provenance.details}
        />

        <p className="muted" style={{ fontSize: 12, marginTop: 22 }}>
          Figures marked <em>est.</em> are approximate; <em>n/a</em> means the measure
          isn&rsquo;t used at this school, and &mdash; means we don&rsquo;t have it. Always
          verify on the official site.
        </p>
      </div>
    </div>
  );
}
