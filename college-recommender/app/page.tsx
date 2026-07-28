"use client";

import { useState } from "react";

import { CultureSliders } from "@/components/CultureSliders";
import { ResultCard } from "@/components/ResultCard";
import { CENTRED_PREFS, type CulturePrefs, type RecommendationResponse } from "@/lib/contract";
import { MAJORS } from "@/lib/majors";

type Status =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; response: RecommendationResponse }
  | { kind: "error"; message: string };

const FIELD =
  "mt-1 w-full rounded border border-neutral-300 px-2 py-1 dark:border-neutral-700 dark:bg-neutral-900";

export default function Home() {
  const [gpa, setGpa] = useState("3.8");
  const [sat, setSat] = useState("");
  const [major, setMajor] = useState("Computer Science");
  const [maxNetPrice, setMaxNetPrice] = useState("");
  const [prefs, setPrefs] = useState<CulturePrefs>(CENTRED_PREFS);
  const [status, setStatus] = useState<Status>({ kind: "idle" });

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setStatus({ kind: "loading" });

    const body = {
      profile: {
        gpa: Number(gpa),
        ...(sat ? { sat: Number(sat) } : {}),
        intended_major: major,
        culture_prefs: prefs,
        ...(maxNetPrice ? { preferences: { max_tuition: Number(maxNetPrice) } } : {}),
      },
      top_k: 8,
    };

    try {
      const res = await fetch("/api/recommend", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const payload = await res.json();
      if (!res.ok) {
        // A failure must never be indistinguishable from "no matches".
        setStatus({
          kind: "error",
          message:
            res.status === 503
              ? "Can't reach the recommendation service. Is the stack running?"
              : res.status === 400
                ? "That profile didn't validate. Check the GPA and SAT ranges."
                : `The recommendation service failed (${payload?.status ?? res.status}).`,
        });
        return;
      }
      setStatus({ kind: "ok", response: payload as RecommendationResponse });
    } catch {
      setStatus({ kind: "error", message: "Network error. Is the app still running?" });
    }
  }

  const results = status.kind === "ok" ? status.response.results : [];

  return (
    <main className="mx-auto max-w-3xl p-6">
      <h1 className="text-2xl font-semibold">UniMatch</h1>
      <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
        364 real universities, scored on academics, cost, fit and campus culture.
      </p>

      <form onSubmit={submit} className="mt-6 space-y-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="text-sm font-medium">GPA</span>
            <input
              type="number" required min={0} max={4} step={0.01} value={gpa}
              onChange={(e) => setGpa(e.target.value)} className={FIELD}
            />
          </label>

          <label className="block">
            <span className="text-sm font-medium">
              SAT <span className="font-normal text-neutral-500">(optional)</span>
            </span>
            <input
              type="number" min={400} max={1600} step={10} value={sat}
              onChange={(e) => setSat(e.target.value)} className={FIELD}
            />
          </label>

          <label className="block">
            <span className="text-sm font-medium">Intended major</span>
            <select value={major} onChange={(e) => setMajor(e.target.value)} className={FIELD}>
              {MAJORS.map((m) => (
                <option key={m} value={m}>{m}</option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="text-sm font-medium">
              Max net price per year{" "}
              <span className="font-normal text-neutral-500">(after aid)</span>
            </span>
            <input
              type="number" min={0} step={1000} value={maxNetPrice} placeholder="no limit"
              onChange={(e) => setMaxNetPrice(e.target.value)} className={FIELD}
            />
          </label>
        </div>

        <CultureSliders value={prefs} onChange={setPrefs} />

        <button
          type="submit"
          disabled={status.kind === "loading"}
          className="rounded bg-sky-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {status.kind === "loading" ? "Matching…" : "Find my matches"}
        </button>
      </form>

      {status.kind === "error" && (
        <p
          role="alert"
          className="mt-6 rounded border border-rose-300 bg-rose-50 p-3 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950 dark:text-rose-200"
        >
          {status.message}
        </p>
      )}

      {status.kind === "ok" && results.length === 0 && (
        <p className="mt-6 rounded border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
          No schools matched. Try raising your maximum net price or choosing a
          different major.
        </p>
      )}

      {status.kind === "ok" && results.length > 0 && (
        <section className="mt-8">
          <h2 className="text-lg font-semibold">
            Your matches{" "}
            <span className="text-sm font-normal text-neutral-500">
              (confidence {Math.round(status.response.confidence * 100)}%)
            </span>
          </h2>
          <ul className="mt-3 space-y-3">
            {results.map((result, index) => (
              <ResultCard key={result.university_id} result={result} rank={index + 1} />
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
