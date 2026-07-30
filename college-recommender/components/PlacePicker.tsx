"use client";

/** Toggle tiles for a list-valued preference. Selecting nothing means "no
 *  preference", which the scorer treats as a full match rather than neutral. */
export function PlacePicker<T extends string>({
  legend,
  hint,
  options,
  selected,
  onChange,
}: {
  legend: string;
  hint: string;
  options: readonly { value: T; label: string }[];
  selected: T[];
  onChange: (next: T[]) => void;
}) {
  const toggle = (value: T) =>
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]);

  return (
    <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
      <legend className="fld">{legend}</legend>
      <p className="muted" style={{ fontSize: 12.5, margin: "0 0 10px" }}>
        {hint}
      </p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            className={`chip ${selected.includes(option.value) ? "on" : ""}`}
            aria-pressed={selected.includes(option.value)}
            onClick={() => toggle(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
    </fieldset>
  );
}
