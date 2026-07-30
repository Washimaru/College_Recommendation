import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { CompareTable } from "./CompareTable";
import type { ListedSchool } from "@/lib/profileStore";

afterEach(cleanup);

const CULTURE = { collab: 0.5, quirky: 0.5, idealist: 0.5, research: 0.5, spirit: 0.5, seminar: 0.5 };

function school(id: string, over: Partial<ListedSchool["university"]> = {}): ListedSchool {
  return {
    id,
    name: `School ${id}`,
    fit: 0.79,
    tier: "reach",
    university: {
      country: "USA", location: "CA", region: "West", setting: "urban", type: "Private",
      avg_gpa: 3.95, avg_sat: 1560, acceptance_rate: 0.046, net_price: 20111,
      enrollment: 4600, size: "small", majors: ["Engineering"], culture: CULTURE,
      provenance: { avg_sat: "observed", acceptance_rate: "observed" },
      ...over,
    },
  };
}

describe("CompareTable", () => {
  it("renders one column per school", () => {
    render(<CompareTable schools={[school("a"), school("b")]} />);

    expect(screen.getByText("School a")).toBeTruthy();
    expect(screen.getByText("School b")).toBeTruthy();
  });

  it("shows the fit percentage", () => {
    render(<CompareTable schools={[school("a")]} />);

    expect(screen.getByText("79%")).toBeTruthy();
  });

  it("renders a not_applicable stat as n/a, never zero", () => {
    render(
      <CompareTable
        schools={[school("a", { avg_sat: null, provenance: { avg_sat: "not_applicable" } })]}
      />,
    );

    expect(screen.getByText("n/a")).toBeTruthy();
    expect(screen.queryByText("0")).toBeNull();
  });

  it("renders an absent stat as an em dash", () => {
    render(
      <CompareTable
        schools={[
          school("a", { acceptance_rate: null, provenance: { acceptance_rate: "absent" } }),
        ]}
      />,
    );

    expect(screen.getByText("—")).toBeTruthy();
  });
});
