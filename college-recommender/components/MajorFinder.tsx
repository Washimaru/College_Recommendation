"use client";

import { useMemo, useState } from "react";

import type { University } from "@/lib/contract";
import { recommendMajors, WORK_AXES, type WorkAxes } from "@/lib/majorFinder";
import { COURSE_TAGS } from "@/lib/majorsData";

const CENTRED: WorkAxes = { people: 0.5, applied: 0.5, creative: 0.5 };

/**
 * Suggests fields of study from the courses you enjoyed, your activities and
 * how you like to work. Each suggestion links back to the catalog, so a major
 * is never a dead end - you can see which schools are strong in it.
 */
export function MajorFinder({
  catalog,
  onOpen,
}: {
  catalog: University[] | null;
  onOpen: (uni: University) => void;
}) {
  const [courses, setCourses] = useState<Set<string>>(new Set());
  const [activities, setActivities] = useState("");
  const [axes, setAxes] = useState<WorkAxes>(CENTRED);
  const [submitted, setSubmitted] = useState(false);

  const ranked = useMemo(
    () => recommendMajors({ courses, activities, axes }),
    [courses, activities, axes],
  );

  const toggleCourse = (course: string) =>
    setCourses((current) => {
      const next = new Set(current);
      if (next.has(course)) next.delete(course);
      else next.add(course);
      return next;
    });

  /** Schools in the catalog that list this major, best-known first. */
  const schoolsFor = (majorName: string): University[] => {
    if (!catalog) return [];
    const needle = majorName.split(" / ")[0].toLowerCase();
    return catalog
      .filter((uni) => uni.majors.some((m) => m.toLowerCase().includes(needle)))
      .slice(0, 6);
  };

  return (
    <section className="section" id="majorfinder">
      <h2>Major Finder</h2>
      <p className="lead">
        Not sure what to study? Tell us what you enjoyed and how you like to work — we&rsquo;ll
        suggest fields, show where each tends to lead, and point you at schools strong in it.
      </p>

      <div className="panel">
        <label className="fld">
          Courses you enjoyed <span style={{ color: "var(--faint)" }}>(pick any)</span>
        </label>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 20 }}>
          {COURSE_TAGS.map((course) => (
            <button
              key={course}
              type="button"
              className={`chip ${courses.has(course) ? "on" : ""}`}
              onClick={() => toggleCourse(course)}
            >
              {course}
            </button>
          ))}
        </div>

        <label className="fld" htmlFor="mf-activities">
          Your activities &amp; interests{" "}
          <span style={{ color: "var(--faint)" }}>(comma-separated)</span>
        </label>
        <input
          id="mf-activities"
          type="text"
          value={activities}
          onChange={(e) => setActivities(e.target.value)}
          placeholder="e.g. robotics, debate, volunteering, jazz band"
        />

        <p className="fld" style={{ marginTop: 22 }}>
          How you like to work
        </p>
        {WORK_AXES.map((axis) => (
          <div key={axis.key} className="slider-row">
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={axes[axis.key]}
              aria-label={`${axis.left} to ${axis.right}`}
              onChange={(e) => setAxes({ ...axes, [axis.key]: Number(e.target.value) })}
            />
            <div className="slider-ends">
              <span>{axis.left}</span>
              <span>{axis.right}</span>
            </div>
          </div>
        ))}

        <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
          <button className="btn" type="button" onClick={() => setSubmitted(true)}>
            ✨ Recommend my majors
          </button>
          <button
            className="btn ghost"
            type="button"
            onClick={() => {
              setCourses(new Set());
              setActivities("");
              setAxes(CENTRED);
              setSubmitted(false);
            }}
          >
            Reset
          </button>
        </div>
      </div>

      {submitted && (
        <div className="cards" style={{ marginTop: 22 }}>
          {ranked.slice(0, 6).map(({ major, score, reasons }) => {
            const schools = schoolsFor(major.name);
            return (
              <div key={major.name} className="card" style={{ cursor: "default" }}>
                <div className="card-head">
                  <div>
                    <h3>{major.name}</h3>
                    <div className="loc">{major.cat}</div>
                  </div>
                  <span className="tier target">{score}% match</span>
                </div>

                <p style={{ margin: "10px 0 0", fontSize: 14 }}>{major.blurb}</p>

                {reasons.length > 0 && (
                  <p className="muted" style={{ fontSize: 12.5, margin: "8px 0 0" }}>
                    Why: {reasons.join(" · ")}
                  </p>
                )}

                <dl className="stats">
                  <div>
                    <dt>Typical salary</dt>
                    <dd>{major.out.salary}</dd>
                  </div>
                  <div>
                    <dt>Grad school</dt>
                    <dd>{major.out.grad}</dd>
                  </div>
                </dl>

                <p style={{ fontSize: 13, marginTop: 12 }}>
                  <b>Where it leads:</b> {major.out.jobs.join(" · ")}
                </p>
                <p className="muted" style={{ fontSize: 12.5, marginTop: 6 }}>
                  {major.out.note}
                </p>

                {schools.length > 0 && (
                  <>
                    <p className="fld" style={{ marginTop: 16, marginBottom: 6 }}>
                      Schools strong in this
                    </p>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                      {schools.map((uni) => (
                        <button
                          key={uni.id}
                          type="button"
                          className="chip"
                          onClick={() => onOpen(uni)}
                        >
                          {uni.name}
                        </button>
                      ))}
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}

      <p className="muted" style={{ fontSize: 12, marginTop: 16 }}>
        Salary and graduate-study figures are approximate — salary anchors from NACE Class of
        2024 where noted, grad-school shares are estimates.
      </p>
    </section>
  );
}
