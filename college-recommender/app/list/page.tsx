"use client";

import { formatStat, tierLabel } from "@/lib/format";
import { analyseList, SAFETY_MAX, SAFETY_MIN } from "@/lib/listAnalysis";
import { useProfileStore } from "@/lib/profileStore";
import { useSchoolModal } from "@/lib/useSchoolModal";

export default function ListPage() {
  const { list, removeFromList } = useProfileStore();
  const { open, modal } = useSchoolModal();
  const analysis = analyseList(list);

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
            Your list is <b>{analysis.total} schools</b>: {analysis.reach} reaches,{" "}
            {analysis.target} targets, {analysis.safety} safeties
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
