"use client";

import { AXIS_LABELS, CULTURE_AXES, type CulturePrefs } from "@/lib/contract";

/**
 * Six bipolar axes. The midpoint means "no preference" and the scorer weights
 * each axis by how far it was moved from centre, so an untouched slider costs
 * a school nothing. That is not obvious from looking at a centred control, so
 * the copy says it explicitly.
 */
export function CultureSliders({
  value,
  onChange,
}: {
  value: CulturePrefs;
  onChange: (next: CulturePrefs) => void;
}) {
  return (
    <fieldset className="space-y-4">
      <legend className="text-sm font-medium">What kind of campus suits you?</legend>
      <p className="text-xs text-neutral-500 dark:text-neutral-400">
        Drag only the ones you care about — anything left in the middle is treated as
        &ldquo;no preference&rdquo; and won&rsquo;t count against any school.
      </p>

      {CULTURE_AXES.map((axis) => (
        <div key={axis} className="space-y-1">
          <input
            id={`axis-${axis}`}
            aria-label={`${AXIS_LABELS[axis].left} to ${AXIS_LABELS[axis].right}`}
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={value[axis]}
            onChange={(event) =>
              onChange({ ...value, [axis]: Number(event.target.value) })
            }
            className="w-full accent-sky-600"
          />
          <div className="flex justify-between text-xs text-neutral-500 dark:text-neutral-400">
            <span>{AXIS_LABELS[axis].left}</span>
            <span>{AXIS_LABELS[axis].right}</span>
          </div>
        </div>
      ))}
    </fieldset>
  );
}
