"use client";

import { useState } from "react";

import type { Activity, ActivityKind } from "@/lib/contract";

const KINDS: ActivityKind[] = [
  "competition", "club", "research", "volunteering", "sport", "arts", "work", "other",
];

/** Ask the server what an activity matches. The endpoint shares one table with
 *  the scorer, so what we show is exactly what will be scored. */
async function classify(activity: Activity): Promise<string[]> {
  try {
    const res = await fetch("/api/classify", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        name: activity.name,
        kind: activity.kind,
        description: activity.description ?? null,
      }),
    });
    if (!res.ok) return [];
    return (await res.json()).subjects as string[];
  } catch {
    // Recognition is advisory. Failing to reach it must never block entry.
    return [];
  }
}

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

  const add = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    const activity: Activity = { name: trimmed, kind };
    const next = [...activities, { ...activity, subjects: await classify(activity) }];
    onChange(next);
    setName("");
  };

  const explain = async (index: number, description: string) => {
    const updated = { ...activities[index], description };
    const next = [...activities];
    next[index] = { ...updated, subjects: await classify(updated) };
    onChange(next);
  };

  return (
    <div>
      <p className="lead" style={{ fontSize: 14 }}>
        Competitions, clubs, research, jobs — whatever you actually spend time on. We&rsquo;ll
        tell you what we recognised, and you can explain anything we miss.
      </p>

      <div style={{ display: "flex", gap: 10, alignItems: "flex-end", flexWrap: "wrap" }}>
        <div style={{ flex: "2 1 240px" }}>
          <label className="fld" htmlFor="act-name">
            What you did
          </label>
          <input
            id="act-name" type="text" value={name}
            placeholder="e.g. FIRST Robotics, Model UN, hospital volunteering"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void add();
              }
            }}
          />
        </div>
        <div style={{ flex: "1 1 140px" }}>
          <label className="fld" htmlFor="act-kind">
            Kind
          </label>
          <select
            id="act-kind" value={kind}
            onChange={(e) => setKind(e.target.value as ActivityKind)}
          >
            {KINDS.map((k) => (
              <option key={k} value={k}>{k[0].toUpperCase() + k.slice(1)}</option>
            ))}
          </select>
        </div>
        <button type="button" className="btn ghost" onClick={() => void add()}>
          Add
        </button>
      </div>

      {activities.length > 0 && (
        <div style={{ marginTop: 16, display: "grid", gap: 12 }}>
          {activities.map((activity, index) => {
            const recognised = (activity.subjects ?? []).length > 0;
            return (
              <div key={`${activity.name}-${index}`} className="qcard">
                <div className="card-head">
                  <div>
                    <b style={{ fontSize: 14.5 }}>{activity.name}</b>
                    <span className="muted" style={{ fontSize: 12.5 }}> · {activity.kind}</span>
                  </div>
                  <button
                    type="button" className="chip"
                    onClick={() => onChange(activities.filter((_, i) => i !== index))}
                  >
                    Remove
                  </button>
                </div>

                {recognised ? (
                  <p style={{ margin: "8px 0 0", fontSize: 13, color: "var(--good)" }}>
                    recognised as: {(activity.subjects ?? []).join(", ")}
                  </p>
                ) : (
                  <p style={{ margin: "8px 0 0", fontSize: 13, color: "var(--warn)" }}>
                    not recognised — tell us what you did and we&rsquo;ll try again
                  </p>
                )}

                <label
                  className="fld"
                  htmlFor={`explain-${index}`}
                  style={{ marginTop: 10 }}
                >
                  Explain {activity.name} <span style={{ color: "var(--faint)" }}>(optional)</span>
                </label>
                <input
                  id={`explain-${index}`}
                  type="text"
                  maxLength={500}
                  defaultValue={activity.description ?? ""}
                  placeholder="e.g. I wrote the code for our robot's autonomous vision system"
                  onBlur={(e) => void explain(index, e.target.value)}
                />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
