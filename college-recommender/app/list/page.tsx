"use client";

import Link from "next/link";

import { formatStat, tierLabel } from "@/lib/format";
import { analyseList, SAFETY_MAX, SAFETY_MIN, suggestGaps } from "@/lib/listAnalysis";
import { useProfileStore } from "@/lib/profileStore";
import { useSchoolModal } from "@/lib/useSchoolModal";

export default function ListPage() {
  const { list, removeFromList, addToList, results } = useProfileStore();
  const { open, modal } = useSchoolModal();
  const analysis = analyseList(list);
  const matches = results?.results ?? [];
  const suggestions = suggestGaps(list, matches);

  if (list.length === 0) {
    return (
      <main className="wrap">
        <section className="section">
          <h2>My college list</h2>
          <p className="lead">
            Nothing here yet. Add schools from your matches or from Browse, and we&rsquo;ll show
            you how balanced the list is.
          </p>
        </section>
      </main>
    );
  }

  return (
    <main className="wrap">
      <section className="section">
        <h2>My college list</h2>

        <div className="panel" style={{ marginBottom: 22 }}>
          <p style={{ margin: 0, fontSize: 15 }}>
            Your list is <b>{analysis.total} schools</b>:{" "}
            {analysis.extremeReach > 0 && <>{analysis.extremeReach} extreme reaches, </>}
            {analysis.reach} reaches, {analysis.target} targets, {analysis.safety} safeties
            {analysis.unknown > 0 && <> · {analysis.unknown} without a tier</>}.
          </p>

          {analysis.needsMoreSafeties ? (
            <p className="muted" style={{ marginBottom: 0, fontSize: 14 }}>
              Safeties are {Math.round(analysis.safetyShare * 100)}% of your list. A common
              suggestion is {Math.round(SAFETY_MIN * 100)}–{Math.round(SAFETY_MAX * 100)}%, about{" "}
              {analysis.targetRange[0] === analysis.targetRange[1]
                ? `${analysis.targetRange[0]} school${analysis.targetRange[0] === 1 ? "" : "s"}`
                : `${analysis.targetRange[0]}–${analysis.targetRange[1]} schools`}
              . That is a rule of thumb rather than something we measured.
            </p>
          ) : (
            <p className="muted" style={{ marginBottom: 0, fontSize: 14 }}>
              Safeties are {Math.round(analysis.safetyShare * 100)}% of your list, inside the
              usual {Math.round(SAFETY_MIN * 100)}–{Math.round(SAFETY_MAX * 100)}% suggestion.
            </p>
          )}

          {analysis.unknown > 0 && (
            <p className="muted" style={{ fontSize: 13, marginBottom: 0 }}>
              Some entries have no tier because your profile had no GPA when they were added.
            </p>
          )}
        </div>

        {analysis.needsMoreSafeties && (
          <div className="panel" style={{ marginBottom: 22 }}>
            {suggestions.length > 0 ? (
              <>
                <p style={{ margin: "0 0 4px", fontSize: 15, fontWeight: 650 }}>
                  From your own matches, these would be safeties for you
                </p>
                <p className="muted" style={{ fontSize: 13, margin: "0 0 12px" }}>
                  Only schools you were already matched with — we don&rsquo;t reach into the
                  catalog for names you haven&rsquo;t seen.
                </p>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
                  {suggestions.map((s) => (
                    <div key={s.id} className="qcard" style={{ margin: 0, flex: "1 1 220px" }}>
                      <div className="card-head">
                        <div style={{ minWidth: 0 }}>
                          <b style={{ fontSize: 14.5 }}>{s.name}</b>
                          <div className="loc">
                            {s.university.location} · {s.university.country}
                          </div>
                        </div>
                        {s.fit !== null && (
                          <span className="tier safety">{Math.round(s.fit * 100)}% fit</span>
                        )}
                      </div>
                      <div style={{ display: "flex", gap: 8, marginTop: 10, flexWrap: "wrap" }}>
                        <button
                          type="button"
                          className="chip"
                          onClick={() => open({ name: s.name, university: s.university })}
                        >
                          Full profile
                        </button>
                        <button type="button" className="chip on" onClick={() => addToList(s)}>
                          Add to my list
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </>
            ) : matches.length === 0 ? (
              <p className="muted" style={{ margin: 0, fontSize: 14 }}>
                We could suggest safeties from your matches, but you haven&rsquo;t run a match
                yet. <Link href="/">Fill in your profile</Link> and we&rsquo;ll draw suggestions
                from what comes back — never from schools you haven&rsquo;t seen.
              </p>
            ) : (
              <p className="muted" style={{ margin: 0, fontSize: 14 }}>
                Nothing left to suggest: your matches turned up no safeties you haven&rsquo;t
                already listed. Widening your budget or country scope on{" "}
                <Link href="/">your profile</Link> would give us more to work with.
              </p>
            )}
          </div>
        )}

        <div className="cards">
          {list.map((school) => {
            const price = formatStat(
              school.university.net_price,
              school.university.provenance.net_price,
              "money",
            );
            return (
              <div key={school.id} className="card" role="group">
                <div className="card-head">
                  <div>
                    <h3>{school.name}</h3>
                    <div className="loc">
                      {school.university.location} · {school.university.country} ·{" "}
                      {price.text} net
                    </div>
                  </div>
                  {tierLabel(school.tier) && (
                    <span className={`tier ${school.tier}`}>{tierLabel(school.tier)}</span>
                  )}
                </div>

                <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
                  <button
                    type="button" className="chip"
                    onClick={() => open({ name: school.name, university: school.university })}
                  >
                    Full profile
                  </button>
                  {school.university.url && (
                    <a
                      className="chip" href={`https://${school.university.url.replace(/^https?:\/\//, "")}`}
                      target="_blank" rel="noreferrer noopener"
                    >
                      Apply / official site ↗
                    </a>
                  )}
                  {school.university.net_price_calculator_url && (
                    <a
                      className="chip" href={school.university.net_price_calculator_url}
                      target="_blank" rel="noreferrer noopener"
                    >
                      What you&rsquo;d actually pay ↗
                    </a>
                  )}
                  <button type="button" className="chip" onClick={() => removeFromList(school.id)}>
                    Remove
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </section>
      {modal}
    </main>
  );
}
