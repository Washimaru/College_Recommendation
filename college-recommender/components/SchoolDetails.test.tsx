import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { SchoolDetails as Details } from "@/lib/contract";
import { SchoolDetailSections } from "./SchoolDetails";

afterEach(cleanup);

describe("SchoolDetailSections - Notable faculty", () => {
  it("renders a single faculty string", () => {
    const details: Details = { faculty: "Jane Doe, Nobel laureate in Physics." };
    render(<SchoolDetailSections details={details} provenance="web_verified" />);

    expect(screen.getByText("Notable faculty")).toBeTruthy();
    expect(screen.getByText(/Jane Doe, Nobel laureate/)).toBeTruthy();
  });

  it("renders an array of faculty entries as separate items", () => {
    const details: Details = {
      faculty: ["Jane Doe, Physics.", "John Smith, Computer Science."],
    };
    render(<SchoolDetailSections details={details} provenance="web_verified" />);

    expect(screen.getByText("Jane Doe, Physics.")).toBeTruthy();
    expect(screen.getByText("John Smith, Computer Science.")).toBeTruthy();
  });

  it("does not render a faculty section when the school has none", () => {
    const details: Details = { research: { level: "R1" } };
    render(<SchoolDetailSections details={details} provenance="web_verified" />);

    expect(screen.queryByText("Notable faculty")).toBeNull();
  });

  it("carries a verify caveat for faculty claims", () => {
    const details: Details = { faculty: "Jane Doe, Physics." };
    render(<SchoolDetailSections details={details} provenance="web_verified" />);

    expect(screen.getByText(/verify/i)).toBeTruthy();
  });

  it("does not duplicate the verify caveat when the data already carries one", () => {
    const details: Details = {
      faculty: "Jane Doe, Physics. (Faculty change — verify.)",
    };
    render(<SchoolDetailSections details={details} provenance="web_verified" />);

    const matches = screen.getAllByText(/verify/i);
    expect(matches).toHaveLength(1);
  });
});
