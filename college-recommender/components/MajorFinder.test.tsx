import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { MajorFinder } from "./MajorFinder";

afterEach(cleanup);

describe("MajorFinder", () => {
  it("surfaces a catalog error instead of implying no school teaches any major", () => {
    render(
      <MajorFinder
        catalog={null}
        error="Couldn't load the catalog. Is the stack running?"
        onOpen={() => {}}
      />,
    );

    expect(screen.getByText(/couldn't load the catalog/i)).toBeTruthy();
  });

  it("explains why a major's schools are missing when the catalog failed, rather than nothing", () => {
    render(
      <MajorFinder
        catalog={null}
        error="Couldn't load the catalog. Is the stack running?"
        onOpen={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /recommend my majors/i }));

    expect(screen.getAllByText(/catalog service is unreachable/i).length).toBeGreaterThan(0);
  });

  it("shows no error notice when the catalog loaded fine", () => {
    render(<MajorFinder catalog={[]} error={null} onOpen={() => {}} />);

    expect(screen.queryByText(/couldn't load/i)).toBeNull();
  });
});

/**
 * The Major Finder is the one place a student asks "who teaches this?", and
 * until now it could only answer from the editorial strengths list — six
 * entries per school, which cannot say a school teaches something it does not
 * boast about, and can never say a school teaches nothing at all.
 */
describe("MajorFinder — federal degree data", () => {
  const CULTURE = {
    collab: 0.5, quirky: 0.5, idealist: 0.5, research: 0.5, spirit: 0.5, seminar: 0.5,
  };

  function school(
    id: string,
    majors: string[],
    programs: { name: string; share: number }[] | null,
  ) {
    return {
      id,
      name: `School ${id}`,
      country: "USA",
      location: "Boston, MA",
      region: "Northeast" as const,
      setting: "urban" as const,
      type: "Private" as const,
      avg_gpa: 3.6,
      size: "medium" as const,
      majors,
      culture: CULTURE,
      provenance: {},
      programs,
    };
  }

  // Biology is among the suggestions an untouched form produces, so these
  // assertions run against a card that is actually on screen.
  const BIO = "Biological & Biomedical Sciences";
  const CATALOG = [
    school("a", ["Biology"], [{ name: BIO, share: 0.3 }]),
    // Teaches it, does not boast about it — invisible to the editorial list.
    school("b", ["Music"], [{ name: BIO, share: 0.05 }]),
    school("c", ["Music"], [{ name: "Visual & Performing Arts", share: 0.4 }]),
    // Abroad: never measured, and must not be counted as awarding none.
    { ...school("d", ["Music"], null), country: "UK", region: "International" as const },
  ];

  function findMajors() {
    render(<MajorFinder catalog={CATALOG} error={null} onOpen={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /recommend my majors/i }));
  }

  it("reports how many schools award degrees in the area", () => {
    findMajors();

    expect(screen.getAllByText(/2 schools award degrees/i).length).toBeGreaterThan(0);
  });

  it("says how many award none — the claim the strengths list cannot make", () => {
    findMajors();

    expect(screen.getAllByText(/1 awards none/i).length).toBeGreaterThan(0);
  });

  it("counts unmeasured schools separately rather than as a no", () => {
    findMajors();

    expect(screen.getAllByText(/1 not measured/i).length).toBeGreaterThan(0);
  });

  it("surfaces a school that teaches the field without listing it as a strength", () => {
    findMajors();

    expect(screen.getAllByText("School b").length).toBeGreaterThan(0);
  });
});
