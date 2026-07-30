import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useSchoolModal, type Openable } from "./useSchoolModal";
import type { Result, University, UniversitySummary } from "./contract";

afterEach(cleanup);

const CULTURE = {
  collab: 0.5,
  quirky: 0.5,
  idealist: 0.5,
  research: 0.5,
  spirit: 0.5,
  seminar: 0.5,
};

const SUMMARY: UniversitySummary = {
  country: "USA",
  location: "Cambridge, MA",
  region: "Northeast",
  setting: "urban",
  type: "Private",
  avg_gpa: 3.95,
  size: "small",
  majors: ["Engineering"],
  culture: CULTURE,
  provenance: {},
};

function Probe({ school }: { school: Openable }) {
  const { open, modal } = useSchoolModal();
  return (
    <>
      <button type="button" onClick={() => open(school)}>
        open
      </button>
      {modal}
    </>
  );
}

/** Renders the probe and opens the modal, so assertions run against real output. */
function openWith(school: Openable) {
  render(<Probe school={school} />);
  fireEvent.click(screen.getByRole("button", { name: "open" }));
}

describe("useSchoolModal", () => {
  it("shows the admit tier when a Result names it admit_tier", () => {
    // Regression: the hook read only `admitTier`, so every modal opened from a
    // match card lost its Reach/Target/Safety badge while the card kept one.
    const result: Result = {
      university_id: "mit",
      name: "MIT",
      score: 0.82,
      rationale: "Strong engineering match.",
      admit_tier: "reach",
      university: SUMMARY,
    };

    openWith(result);

    expect(screen.getByText(/reach/i)).toBeTruthy();
  });

  it("still accepts the camelCase spelling", () => {
    openWith({ name: "MIT", university: SUMMARY, admitTier: "safety" });

    expect(screen.getByText(/safety/i)).toBeTruthy();
  });

  it("accepts a whole University, which carries no tier of its own", () => {
    // Browse and Major Finder pass this shape: a University is its own summary.
    const uni: University = { ...SUMMARY, id: "mit", name: "MIT" };

    openWith(uni);

    expect(screen.getAllByText(/MIT/).length).toBeGreaterThan(0);
  });
});
