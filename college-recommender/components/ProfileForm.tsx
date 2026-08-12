"use client";

import { useState } from "react";
import { Sparkles } from "lucide-react";

import { ActivitiesInput } from "@/components/ActivitiesInput";
import { MatchResults } from "@/components/MatchResults";
import { PlacePicker } from "@/components/PlacePicker";
import { Questionnaire } from "@/components/Questionnaire";
import { CATALOG_SIZE, RURAL_COUNT } from "@/lib/catalogStats";
import type { InstitutionType, RecommendationResponse, Region, Scope, Setting } from "@/lib/contract";
import { useProfileStore } from "@/lib/profileStore";
import { foldAnswers } from "@/lib/questionnaire";
import { MAJORS } from "@/lib/majors";

type Status =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok" }
  | { kind: "error"; message: string };

const REGIONS: readonly { value: Region; label: string }[] = [
  { value: "Northeast", label: "Northeast" },
  { value: "South", label: "South" },
  { value: "West", label: "West" },
  { value: "Midwest", label: "Midwest" },
  { value: "International", label: "International" },
];

const SETTINGS: readonly { value: Setting; label: string }[] = [
  { value: "urban", label: "Urban" },
  { value: "suburban", label: "Suburban" },
  { value: "rural", label: "Rural" },
];

export function ProfileForm() {
  const {
    form, setForm, answers, setAnswers, activities, setActivities, results, setResults, reset,
  } = useProfileStore();
  // `results` lives in the profile store (session-scoped, like the compare
  // tray) so it survives a route change. `status` stays local: it's purely
  // this render's in-flight/error UI state, not something worth resurrecting
  // on remount. Initialising from `results` means a student who already has
  // matches sees them immediately, without re-running the loop.
  const [status, setStatus] = useState<Status>(() => (results ? { kind: "ok" } : { kind: "idle" }));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setStatus({ kind: "loading" });
    const { culturePrefs, personality } = foldAnswers(answers);

    const body = {
      profile: {
        gpa: Number(form.gpa),
        ...(form.gpaWeighted ? { gpa_weighted: Number(form.gpaWeighted) } : {}),
        ...(form.sat ? { sat: Number(form.sat) } : {}),
        intended_major: form.major,
        culture_prefs: culturePrefs,
        personality,
        activities: activities.map(({ name, kind, years, description }) => ({
          name,
          kind,
          ...(years == null ? {} : { years }),
          ...(description ? { description } : {}),
        })),
        preferences: {
          scope: form.scope,
          regions: form.regions,
          settings: form.settings,
          institution_type: form.institutionType,
          ...(form.maxNetPrice ? { max_tuition: Number(form.maxNetPrice) } : {}),
        },
      },
      top_k: 50,
    };

    try {
      const res = await fetch("/api/recommend", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const payload = await res.json();
      if (!res.ok) {
        setStatus({
          kind: "error",
          message:
            res.status === 503
              ? "Can't reach the recommendation service. Is the stack running?"
              : res.status === 400
                ? "That profile didn't validate — check the GPA and SAT ranges."
                : `The recommendation service failed (${payload?.status ?? res.status}).`,
        });
        return;
      }
      setResults(payload as RecommendationResponse);
      setStatus({ kind: "ok" });
    } catch {
      setStatus({ kind: "error", message: "Network error. Is the app still running?" });
    }
  }

  return (
    <>
      <form onSubmit={submit} className="panel" style={{ marginTop: 8 }}>
        <h2>Where you stand</h2>
        <p className="muted" style={{ fontSize: 13, marginTop: 14, marginBottom: 0 }}>
          We score on the unweighted 4.0 GPA. If your school uses a 5.0 weighted scale, add it
          too — it tells us you took harder classes, but it doesn&rsquo;t change your matches.
          We don&rsquo;t convert between the two scales: schools weight differently, so any
          formula would be a guess.
        </p>
        <div className="grid3" style={{ marginTop: 14 }}>
          <div>
            <label className="fld" htmlFor="gpa">
              Unweighted GPA (4.0 scale)
            </label>
            <input
              id="gpa" type="number" required min={0} max={4} step={0.01}
              value={form.gpa} onChange={(e) => setForm({ ...form, gpa: e.target.value })}
            />
          </div>
          <div>
            <label className="fld" htmlFor="gpaWeighted">
              Weighted GPA <span style={{ color: "var(--faint)" }}>(optional, 5.0 scale)</span>
            </label>
            <input
              id="gpaWeighted" type="number" min={0} max={5} step={0.01} placeholder="e.g. 4.42"
              value={form.gpaWeighted}
              onChange={(e) => setForm({ ...form, gpaWeighted: e.target.value })}
            />
          </div>
          <div>
            <label className="fld" htmlFor="sat">
              SAT <span style={{ color: "var(--faint)" }}>(optional)</span>
            </label>
            <input
              id="sat" type="number" min={400} max={1600} step={10} placeholder="e.g. 1400"
              value={form.sat} onChange={(e) => setForm({ ...form, sat: e.target.value })}
            />
          </div>
          <div>
            <label className="fld" htmlFor="budget">
              Max net price / yr <span style={{ color: "var(--faint)" }}>(after aid)</span>
            </label>
            <input
              id="budget" type="number" min={0} step={1000} placeholder="no limit"
              value={form.maxNetPrice}
              onChange={(e) => setForm({ ...form, maxNetPrice: e.target.value })}
            />
          </div>
        </div>

        <div className="grid2" style={{ marginTop: 18 }}>
          <div>
            <label className="fld" htmlFor="major">
              Intended major / field
            </label>
            <select
              id="major" value={form.major}
              onChange={(e) => setForm({ ...form, major: e.target.value })}
            >
              {MAJORS.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="fld" htmlFor="instType">
              Public or private
            </label>
            <select
              id="instType" value={form.institutionType ?? ""}
              onChange={(e) =>
                setForm({
                  ...form,
                  institutionType: (e.target.value || null) as InstitutionType | null,
                })
              }
            >
              <option value="">Either</option>
              <option value="Public">Public only</option>
              <option value="Private">Private only</option>
            </select>
          </div>
        </div>

        <h2 style={{ marginTop: 30 }}>Where you want to be</h2>
        <div style={{ marginTop: 14 }}>
          <PlacePicker
            legend="Region"
            hint="A preference, not a filter — a great fit elsewhere still appears."
            options={REGIONS}
            selected={form.regions}
            onChange={(regions) => setForm({ ...form, regions })}
          />
        </div>
        <div style={{ marginTop: 20 }}>
          <PlacePicker
            legend="Campus setting"
            hint={`Also a preference. Only ${RURAL_COUNT} of ${CATALOG_SIZE} schools are rural, so this nudges rather than excludes.`}
            options={SETTINGS}
            selected={form.settings}
            onChange={(settings) => setForm({ ...form, settings })}
          />
        </div>
        <div style={{ marginTop: 20, maxWidth: 360 }}>
          <label className="fld" htmlFor="scope">
            Country
          </label>
          <select
            id="scope" value={form.scope}
            onChange={(e) => setForm({ ...form, scope: e.target.value as Scope })}
          >
            <option value="both">Anywhere — US and international</option>
            <option value="usa">United States only</option>
            <option value="international">Outside the US only</option>
          </select>
        </div>

        <h2 style={{ marginTop: 30 }}>About you</h2>
        <Questionnaire answers={answers} onChange={setAnswers} />

        <h2 style={{ marginTop: 30 }}>What you do</h2>
        <ActivitiesInput activities={activities} onChange={setActivities} />

        <div style={{ display: "flex", gap: 10, marginTop: 24 }}>
          <button className="btn" type="submit" disabled={status.kind === "loading"}>
            {status.kind === "loading" ? (
              "Matching…"
            ) : (
              <>
                <Sparkles size={16} aria-hidden />
                Show my matches
              </>
            )}
          </button>
          <button
            type="button" className="btn ghost"
            onClick={() => {
              reset();
              setStatus({ kind: "idle" });
            }}
          >
            Start over
          </button>
        </div>
      </form>

      {status.kind === "error" && (
        <p role="alert" className="notice error" style={{ marginTop: 22 }}>
          {status.message}
        </p>
      )}

      {status.kind === "ok" && results && <MatchResults response={results} />}
    </>
  );
}
