import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Result } from "@/lib/contract";
import { ResultCard } from "./ResultCard";

afterEach(cleanup);

function result(overrides: Partial<Result["university"]> = {}, tier: Result["admit_tier"] = "target"): Result {
  return {
    university_id: "u1",
    name: "Test University",
    score: 0.9,
    rationale: "Strong on fit.",
    admit_tier: tier,
    university: {
      country: "USA",
      location: "Cambridge, MA",
      avg_gpa: 3.95,
      avg_sat: 1550,
      acceptance_rate: 0.05,
      net_price: 20111,
      enrollment: 4600,
      size: "small",
      majors: ["Computer Science", "Physics"],
      culture: { collab: 0.7, quirky: 0.85, idealist: 0.55, research: 0.75, spirit: 0.35, seminar: 0.55 },
      provenance: { avg_sat: "observed", acceptance_rate: "observed", net_price: "observed" },
      ...overrides,
    },
  };
}

describe("ResultCard", () => {
  it("renders observed stats as plain values", () => {
    render(<ResultCard result={result()} rank={1} onOpen={() => {}} />);

    expect(screen.getByText("1550")).toBeTruthy();
    expect(screen.getByText("5%")).toBeTruthy();
    expect(screen.getByText("$20,111")).toBeTruthy();
  });

  it("does not round the GPA to a whole number", () => {
    render(<ResultCard result={result()} rank={1} onOpen={() => {}} />);

    expect(screen.getByText("3.95")).toBeTruthy();
    expect(screen.queryByText("4")).toBeNull();
  });

  it("renders a not_applicable stat as n/a, never as zero", () => {
    render(
      <ResultCard
        result={result({ avg_sat: null, provenance: { avg_sat: "not_applicable" } })}
        rank={1}
        onOpen={() => {}}
      />,
    );

    expect(screen.getByText("n/a")).toBeTruthy();
    expect(screen.queryByText("0")).toBeNull();
  });

  it("renders an absent stat distinctly from a not_applicable one", () => {
    render(
      <ResultCard
        result={result({ acceptance_rate: null, provenance: { acceptance_rate: "absent" } })}
        rank={1}
        onOpen={() => {}}
      />,
    );

    expect(screen.getByText("—")).toBeTruthy();
    expect(screen.queryByText("0%")).toBeNull();
  });

  it("marks an editorial figure as an estimate", () => {
    render(
      <ResultCard
        result={result({ net_price: 30000, provenance: { net_price: "editorial" } })}
        rank={1}
        onOpen={() => {}}
      />,
    );

    expect(screen.getByText("est.")).toBeTruthy();
  });

  it("renders a genuine zero as a value, not a gap", () => {
    render(
      <ResultCard
        result={result({ net_price: 0, provenance: { net_price: "observed" } })}
        rank={1}
        onOpen={() => {}}
      />,
    );

    expect(screen.getByText("$0")).toBeTruthy();
  });

  it("shows the admit tier badge", () => {
    render(<ResultCard result={result({}, "reach")} rank={1} onOpen={() => {}} />);

    expect(screen.getByText("Reach")).toBeTruthy();
  });

  it("omits the badge when there is no tier", () => {
    render(<ResultCard result={result({}, null)} rank={1} onOpen={() => {}} />);

    for (const label of ["Reach", "Target", "Safety"]) {
      expect(screen.queryByText(label)).toBeNull();
    }
  });

  it("opens the profile when the card is clicked", async () => {
    const opened: string[] = [];
    render(<ResultCard result={result()} rank={1} onOpen={(r) => opened.push(r.name)} />);

    (await screen.findByRole("button")).click();

    expect(opened).toEqual(["Test University"]);
  });
});
