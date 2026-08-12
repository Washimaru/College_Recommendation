import Link from "next/link";

import { CATALOG_SIZE } from "@/lib/catalogStats";

const REPO = "https://github.com/Washimaru/College_Recommendation";

/**
 * Shown in place of the matching form on GitHub Pages.
 *
 * Matching runs a bounded loop across three services and Postgres. Pages serves
 * static files, so this genuinely cannot work here — and a form that silently
 * failed on submit would be worse than one that explains itself. Browse, Major
 * Finder and the college list need only the catalog, so they work in full.
 */
export function StaticDemoNotice() {
  return (
    <section className="section">
      <div className="panel">
        <h2 style={{ marginTop: 0 }}>Matching needs the backend</h2>
        <p className="lead" style={{ fontSize: 15 }}>
          This is the static build on GitHub Pages. Ranking a profile runs a loop across three
          services and a Postgres database, and Pages can only serve files — so rather than give
          you a form that fails when you press it, here is what does work.
        </p>

        <div className="grid2" style={{ marginTop: 18 }}>
          <div>
            <p className="fld" style={{ marginBottom: 8 }}>Working here, in full</p>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 14, lineHeight: 1.7 }}>
              <li>
                <Link href="/browse">Browse</Link> — search all {CATALOG_SIZE} universities, filter by
                region, setting and cost, compare three side by side
              </li>
              <li>
                <Link href="/majors">Major Finder</Link> — find fields that suit you, and the
                schools strong in them
              </li>
              <li>
                <Link href="/list">My college list</Link> — build a list and see how balanced it
                is
              </li>
            </ul>
          </div>
          <div>
            <p className="fld" style={{ marginBottom: 8 }}>Needs the full stack</p>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 14, lineHeight: 1.7 }}>
              <li>Profile matching and fit percentages</li>
              <li>Extreme reach / reach / target / safety tiers</li>
              <li>Activity recognition</li>
            </ul>
          </div>
        </div>

        <p className="fld" style={{ marginTop: 22, marginBottom: 8 }}>
          Run the whole thing locally
        </p>
        <pre
          style={{
            background: "var(--panel2)",
            border: "1px solid var(--line)",
            borderRadius: "var(--r-sm)",
            padding: "12px 14px",
            fontSize: 12.5,
            overflowX: "auto",
            margin: 0,
          }}
        >
          {`git clone ${REPO}.git
cd College_Recommendation
./scripts/setup.sh && cp .env.example .env
docker compose up -d
cd college-recommender && npm install && npm run dev`}
        </pre>
        <p className="muted" style={{ fontSize: 13, marginTop: 10, marginBottom: 0 }}>
          Then open <code>localhost:3000</code> — every page works, against {CATALOG_SIZE} real
          universities.{" "}
          <a href={REPO} target="_blank" rel="noreferrer noopener">
            Source on GitHub ↗
          </a>
        </p>
      </div>
    </section>
  );
}
