import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ProfileProvider, useProfileStore, COMPARE_LIMIT } from "./profileStore";
import type { ListedSchool } from "./profileStore";

const CULTURE = { collab: 0.5, quirky: 0.5, idealist: 0.5, research: 0.5, spirit: 0.5, seminar: 0.5 };

function school(id: string): ListedSchool {
  return {
    id,
    name: `School ${id}`,
    fit: 0.8,
    tier: "target",
    university: {
      country: "USA", location: "CA", region: "West", setting: "urban", type: "Private",
      avg_gpa: 3.7, size: "medium", majors: ["CS"], culture: CULTURE, provenance: {},
    },
  };
}

let store: ReturnType<typeof useProfileStore>;

function Probe() {
  // Reassigning a module-level `let` from inside a rendered component is a
  // standard React Testing Library probe idiom to expose hook state to
  // assertions outside the tree. `react-hooks/globals` (from the new
  // React Compiler-era hook rules) flags it as an impure render, which is a
  // real concern for production components but not for a test-only probe
  // that always re-renders and is never compiled/memoized.
  // eslint-disable-next-line react-hooks/globals
  store = useProfileStore();
  return <span>{store.list.length} listed</span>;
}

function mount() {
  return render(
    <ProfileProvider>
      <Probe />
    </ProfileProvider>,
  );
}

beforeEach(() => localStorage.clear());
afterEach(() => localStorage.clear());

describe("profile store", () => {
  it("starts empty", () => {
    mount();
    expect(screen.getByText("0 listed")).toBeTruthy();
  });

  it("adds and removes list entries", () => {
    mount();
    act(() => store.addToList(school("a")));
    expect(store.isListed("a")).toBe(true);
    act(() => store.removeFromList("a"));
    expect(store.isListed("a")).toBe(false);
  });

  it("never lists the same school twice", () => {
    mount();
    act(() => store.addToList(school("a")));
    act(() => store.addToList(school("a")));
    expect(store.list).toHaveLength(1);
  });

  it("caps the compare tray and refuses rather than evicting", () => {
    mount();
    act(() => {
      for (const id of ["a", "b", "c", "d"]) store.addToCompare(school(id));
    });
    expect(store.compare).toHaveLength(COMPARE_LIMIT);
    expect(store.compare.map((s) => s.id)).toEqual(["a", "b", "c"]);
  });

  it("persists the list across a remount", () => {
    mount();
    act(() => store.addToList(school("a")));
    mount();
    expect(store.isListed("a")).toBe(true);
  });

  it("falls back to empty when stored data is corrupt", () => {
    localStorage.setItem("unimatch.v1", "{not json");
    mount();
    expect(store.list).toEqual([]);
  });
});
