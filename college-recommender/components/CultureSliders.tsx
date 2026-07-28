"use client";

import { AXIS_LABELS, CULTURE_AXES, type CulturePrefs } from "@/lib/contract";

/**
 * Six bipolar axes. The midpoint means "no preference", and the scorer weights
 * each axis by how far it was moved from centre, so an untouched slider costs
 * a school nothing. A centred control otherwise reads as an unanswered
 * question, so the copy says so.
 */
export function CultureSliders({
  value,
  onChange,
}: {
  value: CulturePrefs;
  onChange: (next: CulturePrefs) => void;
}) {
  return (
    <div>
      {CULTURE_AXES.map((axis) => (
        <div key={axis} className="slider-row">
          <input
            id={`axis-${axis}`}
            aria-label={`${AXIS_LABELS[axis].left} to ${AXIS_LABELS[axis].right}`}
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={value[axis]}
            onChange={(event) => onChange({ ...value, [axis]: Number(event.target.value) })}
          />
          <div className="slider-ends">
            <span>{AXIS_LABELS[axis].left}</span>
            <span>{AXIS_LABELS[axis].right}</span>
          </div>
        </div>
      ))}
    </div>
  );
}
