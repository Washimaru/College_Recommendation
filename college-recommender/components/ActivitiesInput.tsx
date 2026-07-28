"use client";

import { useState } from "react";

import type { Activity, ActivityKind } from "@/lib/contract";

const KINDS: ActivityKind[] = [
  "competition",
  "club",
  "research",
  "volunteering",
  "sport",
  "arts",
  "work",
  "other",
];

/**
 * Competitions, clubs and other commitments. These are matched by keyword
 * against what each school is strong in, so the pairing is what scores - a
 * robotics competition helps at an engineering school, not everywhere.
 */
export function ActivitiesInput({
  activities,
  onChange,
}: {
  activities: Activity[];
  onChange: (next: Activity[]) => void;
}) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<ActivityKind>("competition");

  const add = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    onChange([...activities, { name: trimmed, kind }]);
    setName("");
  };

  return (
    <div>
      <p className="lead" style={{ fontSize: 14 }}>
        Competitions, clubs, research, jobs — whatever you actually spend time on. Each one is
        matched against what schools are strong in.
      </p>

      <div style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
        <div style={{ flex: "2 1 240px" }}>
          <label className="fld" htmlFor="act-name">
            What you did
          </label>
          <input
            id="act-name"
            type="text"
            value={name}
            placeholder="e.g. FIRST Robotics, Model UN, hospital volunteering"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add();
              }
            }}
          />
        </div>
        <div style={{ flex: "1 1 140px" }}>
          <label className="fld" htmlFor="act-kind">
            Kind
          </label>
          <select
            id="act-kind"
            value={kind}
            onChange={(e) => setKind(e.target.value as ActivityKind)}
          >
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {k[0].toUpperCase() + k.slice(1)}
              </option>
            ))}
          </select>
        </div>
        <button type="button" className="btn ghost" onClick={add}>
          Add
        </button>
      </div>

      {activities.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 14 }}>
          {activities.map((activity, index) => (
            <button
              key={`${activity.name}-${index}`}
              type="button"
              className="chip on"
              title="Remove"
              onClick={() => onChange(activities.filter((_, i) => i !== index))}
            >
              {activity.name} · {activity.kind} ✕
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
