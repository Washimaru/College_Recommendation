import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProfileProvider } from "@/lib/profileStore";
import { AppShell } from "./AppShell";

/**
 * The shell wraps all four routes, which is why the unreadable-storage notice
 * lives here: recovering to an empty profile is correct, but a student whose
 * saved list disappeared with no explanation cannot tell that from a bug.
 */

vi.mock("next/navigation", () => ({ usePathname: () => "/" }));

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

function mount() {
  return render(
    <ProfileProvider>
      <AppShell>
        <p>page body</p>
      </AppShell>
    </ProfileProvider>,
  );
}

describe("AppShell", () => {
  it("says nothing about storage when there was nothing stored", () => {
    mount();

    expect(screen.queryByText(/couldn.t read your saved profile/i)).toBeNull();
    expect(screen.getByText("page body")).toBeTruthy();
  });

  it("says nothing when the stored profile read cleanly", () => {
    window.localStorage.setItem("unimatch.v1", JSON.stringify({ list: [] }));

    mount();

    expect(screen.queryByText(/couldn.t read your saved profile/i)).toBeNull();
  });

  it("explains an empty session after unreadable storage", () => {
    window.localStorage.setItem("unimatch.v1", "{not json");

    mount();

    expect(screen.getByText(/couldn.t read your saved profile/i)).toBeTruthy();
  });

  it("lets the notice be dismissed", () => {
    window.localStorage.setItem("unimatch.v1", "{not json");
    mount();

    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));

    expect(screen.queryByText(/couldn.t read your saved profile/i)).toBeNull();
  });
});
