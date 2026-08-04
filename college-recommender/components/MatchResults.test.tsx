import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { RecommendationResponse, Result } from "@/lib/contract";
import { ProfileProvider } from "@/lib/profileStore";
import { MatchResults } from "./MatchResults";

afterEach(cleanup);

function renderResults(res: RecommendationResponse) {
  return render(
    <ProfileProvider>
      <MatchResults response={res} />
    </ProfileProvider>,
  );
}

const CULTURE = { collab: 0.5, quirky: 0.5, idealist: 0.5, research: 0.5, spirit: 0.5, seminar: 0.5 };

function result(id: string, tier: Result["admit_tier"]): Result {
  return {
    university_id: id,
    name: `School ${id}`,
    score: 0.8,
    rationale: "because",
    admit_tier: tier,
    university: {
      country: "USA", location: "CA", region: "West", setting: "urban", type: "Private",
      avg_gpa: 3.7, size: "medium", majors: ["CS"], culture: CULTURE, provenance: {},
    },
  };
}

function response(results: Result[]): RecommendationResponse {
  return { results, confidence: 0.9, stop_reason: "R2_confident", trace: [] };
}

describe("MatchResults tier filter", () => {
  it("offers an Extreme reach filter chip alongside the other three tiers", () => {
    renderResults(
      response([
        result("er1", "extreme_reach"),
        result("r1", "reach"),
        result("t1", "target"),
        result("s1", "safety"),
      ]),
    );

    expect(screen.getByRole("button", { name: "Extreme reach" })).toBeTruthy();
  });

  it("filters down to only extreme-reach schools when that chip is toggled on", () => {
    renderResults(
      response([
        result("er1", "extreme_reach"),
        result("r1", "reach"),
        result("t1", "target"),
        result("s1", "safety"),
      ]),
    );

    fireEvent.click(screen.getByRole("button", { name: "Extreme reach" }));

    expect(screen.getByText("School er1")).toBeTruthy();
    expect(screen.queryByText("School r1")).toBeNull();
    expect(screen.queryByText("School t1")).toBeNull();
    expect(screen.queryByText("School s1")).toBeNull();
  });
});
