import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { AdmitTier, UniversitySummary } from "@/lib/contract";
import { ProfileProvider, type ListedSchool } from "@/lib/profileStore";
import ListPage from "./page";

/**
 * The college list route. `lib/listAnalysis.ts` is tested on its own; what is
 * tested here is the page that reads it - the empty state, and that the
 * balance it reports is the balance of the schools actually on the list.
 */

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

const UNIVERSITY: UniversitySummary = {
  country: "USA",
  location: "Cambridge, MA",
  region: "Northeast",
  setting: "urban",
  type: "Private",
  avg_gpa: 3.9,
  avg_sat: 1500,
  acceptance_rate: 0.1,
  net_price: 20000,
  enrollment: 5000,
  size: "small",
  majors: ["Computer Science"],
  culture: { collab: 0.5, quirky: 0.5, idealist: 0.5, research: 0.5, spirit: 0.5, seminar: 0.5 },
  provenance: {},
};

function listed(id: string, tier: AdmitTier): ListedSchool {
  return { id, name: `School ${id}`, fit: 0.8, tier, university: UNIVERSITY };
}

/** The page reads the list from the store, and the store hydrates from
 *  localStorage - so seeding storage exercises the real path a returning
 *  student takes, with no probe reaching into the tree. */
function renderList(schools: ListedSchool[]) {
  window.localStorage.setItem("unimatch.v1", JSON.stringify({ list: schools }));

  return render(
    <ProfileProvider>
      <ListPage />
    </ProfileProvider>,
  );
}

describe("ListPage", () => {
  it("says the list is empty rather than showing a zeroed analysis", () => {
    renderList([]);

    expect(screen.getByText(/Nothing here yet/)).toBeTruthy();
    expect(screen.queryByText(/reaches,/)).toBeNull();
  });

  it("reports the tier balance of the schools on the list", () => {
    renderList([listed("a", "reach"), listed("b", "target"), listed("c", "safety")]);

    expect(screen.getByText(/3 schools/)).toBeTruthy();
    expect(screen.getByText(/1 reaches, 1 targets, 1 safeties/)).toBeTruthy();
  });

  it("flags a list with too few safeties as a rule of thumb, not a measurement", () => {
    renderList([listed("a", "reach"), listed("b", "reach"), listed("c", "reach")]);

    expect(screen.getByText(/rule of thumb/)).toBeTruthy();
  });

  it("does not flag a balanced list", () => {
    renderList([listed("a", "reach"), listed("b", "safety"), listed("c", "safety")]);

    expect(screen.queryByText(/rule of thumb/)).toBeNull();
    expect(screen.getByText(/inside the/)).toBeTruthy();
  });
});
