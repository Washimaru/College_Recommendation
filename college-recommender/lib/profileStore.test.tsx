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

  it("holds recommendation results in memory, not localStorage", () => {
    const response = {
      results: [],
      confidence: 0.9,
      stop_reason: "R2_confident",
      trace: [],
    };
    mount();
    act(() => store.setResults(response));
    expect(store.results).toEqual(response);
    expect(localStorage.getItem("unimatch.v1")).not.toContain("R2_confident");
  });

  it("keeps results when the consuming page unmounts and remounts, because ProfileProvider itself (in the root layout) never does", () => {
    const response = {
      results: [],
      confidence: 0.9,
      stop_reason: "R2_confident",
      trace: [],
    };
    // Simulates a Next.js route change: the outer <ProfileProvider> — mounted
    // once in app/layout.tsx — stays the same React instance across
    // navigation, only its `children` (the page) is swapped. A fresh `render`
    // call would instead create a brand-new provider, which is the wrong
    // simulation and wouldn't prove anything about surviving navigation.
    const { rerender } = render(
      <ProfileProvider>
        <Probe />
      </ProfileProvider>,
    );
    act(() => store.setResults(response));

    rerender(
      <ProfileProvider>
        <div>a different page</div>
      </ProfileProvider>,
    );
    rerender(
      <ProfileProvider>
        <Probe />
      </ProfileProvider>,
    );

    expect(store.results).toEqual(response);
  });

  it("clears results on reset", () => {
    const response = {
      results: [],
      confidence: 0.9,
      stop_reason: "R2_confident",
      trace: [],
    };
    mount();
    act(() => store.setResults(response));
    act(() => store.reset());
    expect(store.results).toBeNull();
  });
});

/**
 * Corrupt stored data recovers to an empty profile, which is right — but it
 * used to happen in silence, so a student whose saved list vanished had no way
 * to tell a bug from a browser wiping their storage.
 */
describe("recovery from unreadable storage", () => {
  it("reports that it recovered when the stored value is not JSON", () => {
    localStorage.setItem("unimatch.v1", "{not json");
    mount();

    expect(store.storageRecovered).toBe(true);
    expect(store.list).toEqual([]);
  });

  it("reports nothing when there was no stored value at all", () => {
    mount();

    expect(store.storageRecovered).toBe(false);
  });

  it("reports nothing when the stored value reads cleanly", () => {
    localStorage.setItem("unimatch.v1", JSON.stringify({ list: [school("a")] }));
    mount();

    expect(store.storageRecovered).toBe(false);
    expect(store.isListed("a")).toBe(true);
  });
});
