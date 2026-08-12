import { cleanup, render, screen } from "@testing-library/react";
import type { ComponentType } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * The three thin route pages. Their components are tested individually; what
 * these check is the wiring - that each route mounts the section it claims to
 * and, for the home route, that a static build says so instead of offering a
 * matching run it cannot perform.
 *
 * Each case re-imports the page after `resetModules()` so `IS_STATIC_DEMO`,
 * read at module scope, is evaluated against that case's env. The provider has
 * to come from the same fresh module graph as the page, or the page's
 * `useProfileStore` looks up a context the provider never populated.
 */

afterEach(() => {
  cleanup();
  vi.resetModules();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

/** Both catalog routes fetch on mount; nothing here should open a socket. */
function stubCatalogFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => Response.json({ universities: [] })),
  );
}

async function renderRoute(load: () => Promise<{ default: ComponentType }>) {
  const [{ default: Page }, { ProfileProvider }] = await Promise.all([
    load(),
    import("@/lib/profileStore"),
  ]);

  return render(
    <ProfileProvider>
      <Page />
    </ProfileProvider>,
  );
}

describe("route pages", () => {
  it("/browse mounts the browse section", async () => {
    stubCatalogFetch();

    await renderRoute(() => import("./browse/page"));

    expect(screen.getByText(/Browse & search all schools/)).toBeTruthy();
  });

  it("/majors mounts the major finder", async () => {
    stubCatalogFetch();

    await renderRoute(() => import("./majors/page"));

    expect(screen.getByRole("heading", { name: /major/i })).toBeTruthy();
  });

  it("/ offers the profile form when the full stack is running", async () => {
    vi.stubEnv("NEXT_PUBLIC_STATIC_DEMO", "");

    await renderRoute(() => import("./page"));

    expect(screen.getByRole("button", { name: /show my matches/i })).toBeTruthy();
  });

  it("/ says so on a static build instead of offering a run it cannot do", async () => {
    vi.stubEnv("NEXT_PUBLIC_STATIC_DEMO", "1");

    await renderRoute(() => import("./page"));

    expect(screen.queryByRole("button", { name: /show my matches/i })).toBeNull();
    expect(screen.getByText(/Browse/)).toBeTruthy();
  });
});
