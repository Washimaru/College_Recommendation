import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { University } from "./contract";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const CULTURE = { collab: 0.5, quirky: 0.5, idealist: 0.5, research: 0.5, spirit: 0.5, seminar: 0.5 };

const UNI: University = {
  id: "u1", name: "Test University", country: "USA", location: "Boston, MA",
  region: "Northeast", setting: "urban", type: "Private",
  avg_gpa: 3.5, size: "medium", majors: ["Biology"], culture: CULTURE, provenance: {},
};

/** `useCatalog`'s cache lives at module scope, so each test needs a fresh
 *  module instance (`vi.resetModules`) to avoid one test's fetch bleeding
 *  into the next — the exact isolation the cache itself must NOT provide
 *  across real page-load boundaries. */
async function freshUseCatalog() {
  vi.resetModules();
  const mod = await import("./useCatalog");
  return mod.useCatalog;
}

function Host({ useCatalog }: { useCatalog: () => { catalog: University[] | null; error: string | null } }) {
  const { catalog, error } = useCatalog();
  if (error) return <div>error: {error}</div>;
  if (!catalog) return <div>loading</div>;
  return <div>loaded {catalog.length}</div>;
}

describe("useCatalog", () => {
  it("fetches the catalog once and does not refetch on a second mount", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ universities: [UNI] }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const useCatalog = await freshUseCatalog();

    const { unmount } = render(<Host useCatalog={useCatalog} />);
    await screen.findByText("loaded 1");
    unmount();

    render(<Host useCatalog={useCatalog} />);
    await screen.findByText("loaded 1");

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("does not cache a failed fetch — a later mount retries", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error("network down"));
    vi.stubGlobal("fetch", fetchMock);
    const useCatalog = await freshUseCatalog();

    const { unmount } = render(<Host useCatalog={useCatalog} />);
    await screen.findByText(/error:/);
    unmount();

    render(<Host useCatalog={useCatalog} />);
    await screen.findByText(/error:/);

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("serves a second mount from the cache even before that mount's own effect runs", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ universities: [UNI] }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const useCatalog = await freshUseCatalog();

    const { unmount } = render(<Host useCatalog={useCatalog} />);
    await screen.findByText("loaded 1");
    unmount();

    // No "loading" flash on the second mount: the cache is already warm.
    render(<Host useCatalog={useCatalog} />);
    expect(screen.getByText("loaded 1")).toBeTruthy();
  });
});
