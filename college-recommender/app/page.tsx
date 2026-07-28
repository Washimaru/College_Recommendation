"use client";

import { useEffect, useState } from "react";

import { ActivitiesInput } from "@/components/ActivitiesInput";
import { Questionnaire } from "@/components/Questionnaire";
import { ResultCard } from "@/components/ResultCard";
import { BrowseSection } from "@/components/BrowseSection";
import { MajorFinder } from "@/components/MajorFinder";
import { UniversityModal } from "@/components/UniversityModal";
import {
  type Activity,
  type RecommendationResponse,
  type University,
  type UniversitySummary,
} from "@/lib/contract";
import { foldAnswers } from "@/lib/questionnaire";
import { MAJORS } from "@/lib/majors";

type Status =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; response: RecommendationResponse }
  | { kind: "error"; message: string };

type Sort = "match" | "price" | "selectivity";

export default function Home() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  // Fetched once and shared: browse searches it, and Major Finder uses it to
  // show which schools are strong in each suggested field.
  const [catalog, setCatalog] = useState<University[] | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [gpa, setGpa] = useState("3.8");
  const [sat, setSat] = useState("");
  const [major, setMajor] = useState("Computer Science");
  const [maxNetPrice, setMaxNetPrice] = useState("");
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [activities, setActivities] = useState<Activity[]>([]);
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [sort, setSort] = useState<Sort>("match");
  const [tiers, setTiers] = useState<string[]>([]);
  // One modal serves both matches and browse; matches add a rationale and tier.
  const [open, setOpen] = useState<{
    name: string;
    university: UniversitySummary;
    rationale?: string;
    admitTier?: "reach" | "target" | "safety" | null;
  } | null>(null);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/universities")
      .then(async (res) => {
        if (!res.ok) throw new Error(String(res.status));
        return res.json();
      })
      .then((body) => {
        if (!cancelled) setCatalog(body.universities as University[]);
      })
      .catch(() => {
        if (!cancelled) setCatalogError("Couldn't load the catalog. Is the stack running?");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setStatus({ kind: "loading" });

    const { culturePrefs, personality } = foldAnswers(answers);

    const body = {
      profile: {
        gpa: Number(gpa),
        ...(sat ? { sat: Number(sat) } : {}),
        intended_major: major,
        culture_prefs: culturePrefs,
        personality,
        activities,
        ...(maxNetPrice ? { preferences: { max_tuition: Number(maxNetPrice) } } : {}),
      },
      top_k: 12,
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
      setStatus({ kind: "ok", response: payload as RecommendationResponse });
      document.getElementById("results")?.scrollIntoView({ behavior: "smooth" });
    } catch {
      setStatus({ kind: "error", message: "Network error. Is the app still running?" });
    }
  }

  const all = status.kind === "ok" ? status.response.results : [];
  const filtered = tiers.length
    ? all.filter((r) => r.admit_tier && tiers.includes(r.admit_tier))
    : all;
  const results = [...filtered].sort((a, b) => {
    if (sort === "price") return (a.university.net_price ?? 1e9) - (b.university.net_price ?? 1e9);
    if (sort === "selectivity")
      return (a.university.acceptance_rate ?? 1) - (b.university.acceptance_rate ?? 1);
    return b.score - a.score;
  });

  const toggleTier = (tier: string) =>
    setTiers((current) =>
      current.includes(tier) ? current.filter((t) => t !== tier) : [...current, tier],
    );

  return (
    <>
      <nav className="nav">
        <div className="nav-inner">
          <a href="#top" className="brand">
            <span className="dot" />
            Uni<b>Match</b>
          </a>
          <div className="nav-links" style={{ marginLeft: "auto" }}>
            <a href="#wizard">Match</a>
            <a href="#browse">Browse</a>
            <a href="#majorfinder">Major Finder</a>
          </div>
          <button
            className="icon-btn"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            title="Toggle theme"
            aria-label="Toggle theme"
          >
            {theme === "dark" ? "🌙" : "☀️"}
          </button>
        </div>
      </nav>

      <div id="top" />

      <header className="hero wrap">
        <span className="eyebrow">Holistic matching · not just filters</span>
        <h1>
          Find the university that <span className="g">fits who you are</span>
        </h1>
        <p>
          Most tools filter by tuition and test scores and hand you a generic list. UniMatch
          sets your hard limits first, then ranks what&rsquo;s left by how each campus actually{" "}
          <i>feels</i> — culture, pace, and the way you like to learn.
        </p>
        <div className="hero-stats">
          <div>
            <b>364</b>
            <span>universities · 26 countries</span>
          </div>
          <div>
            <b>6</b>
            <span>culture dimensions</span>
          </div>
          <div>
            <b>4</b>
            <span>scored dimensions</span>
          </div>
        </div>
      </header>

      <main className="wrap" id="wizard">
        <form onSubmit={submit} className="panel">
          <h2>Your profile &amp; limits</h2>
          <p className="lead" style={{ fontSize: 14 }}>
            Leave anything blank to ignore it.
          </p>

          <div className="grid3">
            <div>
              <label className="fld" htmlFor="gpa">
                Your GPA (4.0 scale)
              </label>
              <input
                id="gpa" type="number" required min={0} max={4} step={0.01}
                value={gpa} onChange={(e) => setGpa(e.target.value)}
              />
            </div>
            <div>
              <label className="fld" htmlFor="sat">
                SAT <span style={{ color: "var(--faint)" }}>(optional)</span>
              </label>
              <input
                id="sat" type="number" min={400} max={1600} step={10} placeholder="e.g. 1400"
                value={sat} onChange={(e) => setSat(e.target.value)}
              />
            </div>
            <div>
              <label className="fld" htmlFor="budget">
                Max net price / yr <span style={{ color: "var(--faint)" }}>(after aid)</span>
              </label>
              <input
                id="budget" type="number" min={0} step={1000} placeholder="no limit"
                value={maxNetPrice} onChange={(e) => setMaxNetPrice(e.target.value)}
              />
            </div>
          </div>

          <div style={{ marginTop: 18 }}>
            <label className="fld" htmlFor="major">
              Intended major / field
            </label>
            <select id="major" value={major} onChange={(e) => setMajor(e.target.value)}>
              {MAJORS.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>

          <h2 style={{ marginTop: 30 }}>About you</h2>
          <Questionnaire answers={answers} onChange={setAnswers} />

          <h2 style={{ marginTop: 30 }}>What you do</h2>
          <ActivitiesInput activities={activities} onChange={setActivities} />

          <div style={{ display: "flex", gap: 10, marginTop: 22 }}>
            <button className="btn" type="submit" disabled={status.kind === "loading"}>
              {status.kind === "loading" ? "Matching…" : "✨ Show my matches"}
            </button>
            <button
              type="button"
              className="btn ghost"
              onClick={() => {
                setAnswers({});
                setActivities([]);
                setStatus({ kind: "idle" });
                setTiers([]);
              }}
            >
              Reset
            </button>
          </div>
        </form>

        {status.kind === "error" && (
          <p role="alert" className="notice error" style={{ marginTop: 22 }}>
            {status.message}
          </p>
        )}

        {status.kind === "ok" && all.length === 0 && (
          <p className="notice empty" style={{ marginTop: 22 }}>
            No schools matched. Try raising your maximum net price or choosing a different
            major.
          </p>
        )}

        {status.kind === "ok" && all.length > 0 && (
          <section className="section" id="results">
            <h2>Your top matches</h2>
            <p className="muted" style={{ fontSize: 14, margin: "0 0 18px" }}>
              {results.length} of {all.length} shown · click any school for its full profile
            </p>

            <div
              style={{
                display: "flex",
                gap: 8,
                flexWrap: "wrap",
                alignItems: "center",
                marginBottom: 18,
              }}
            >
              <span className="muted" style={{ fontSize: 13 }}>
                Sort
              </span>
              {(
                [
                  ["match", "Best match"],
                  ["price", "Lowest price"],
                  ["selectivity", "Most selective"],
                ] as [Sort, string][]
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  className={`chip ${sort === key ? "on" : ""}`}
                  onClick={() => setSort(key)}
                >
                  {label}
                </button>
              ))}
              <span className="muted" style={{ fontSize: 13, marginLeft: 10 }}>
                Filter
              </span>
              {["reach", "target", "safety"].map((tier) => (
                <button
                  key={tier}
                  type="button"
                  className={`chip ${tiers.includes(tier) ? "on" : ""}`}
                  onClick={() => toggleTier(tier)}
                >
                  {tier[0].toUpperCase() + tier.slice(1)}
                </button>
              ))}
            </div>

            <div className="cards">
              {results.map((result, index) => (
                <ResultCard
                  key={result.university_id}
                  result={result}
                  rank={index + 1}
                  onOpen={(r) =>
                    setOpen({
                      name: r.name,
                      university: r.university,
                      rationale: r.rationale,
                      admitTier: r.admit_tier,
                    })
                  }
                />
              ))}
            </div>
          </section>
        )}
      </main>

      <div className="wrap">
        <BrowseSection
          catalog={catalog}
          error={catalogError}
          onOpen={(uni: University) => setOpen({ name: uni.name, university: uni })}
        />
        <MajorFinder
          catalog={catalog}
          onOpen={(uni: University) => setOpen({ name: uni.name, university: uni })}
        />
      </div>

      {open && (
        <UniversityModal
          name={open.name}
          university={open.university}
          rationale={open.rationale}
          admitTier={open.admitTier}
          onClose={() => setOpen(null)}
        />
      )}

      <footer>
        UniMatch · figures are approximate and for exploration only — always verify on
        official sites.
        <br />
        Admitted-GPA and campus-culture ratings are editorial estimates; admissions and cost
        figures come from the U.S. Dept. of Education College Scorecard where available.
      </footer>
    </>
  );
}
