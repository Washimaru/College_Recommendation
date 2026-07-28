"use client";

import { useEffect } from "react";

import { AXIS_LABELS, CULTURE_AXES, type AdmitTier, type UniversitySummary } from "@/lib/contract";
import { formatStat, tierLabel, type StatKind } from "@/lib/format";
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
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const uni = university;
  const tier = tierLabel(admitTier);

  return (
    <div
      className="modal-back"
      role="dialog"
      aria-modal="true"
      aria-label={name}
      onClick={onClose}
    >
      <div className="modal" onClick={(event) => event.stopPropagation()}>
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
        </dl>

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
