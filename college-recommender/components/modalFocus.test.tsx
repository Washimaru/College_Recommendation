import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { UniversitySummary } from "@/lib/contract";
import { ProfileProvider, useProfileStore, type ListedSchool } from "@/lib/profileStore";
import { CompareTray } from "./CompareTray";
import { UniversityModal } from "./UniversityModal";

/**
 * Both dialogs claim `aria-modal="true"`. These check the claim is honoured
 * where it counts - focus lands inside, Tab cannot leave, Escape closes - so
 * the trap cannot be quietly unwired from either one.
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
  avg_gpa: 3.95,
  avg_sat: 1550,
  acceptance_rate: 0.05,
  net_price: 20111,
  enrollment: 4600,
  size: "small",
  majors: ["Computer Science"],
  culture: { collab: 0.7, quirky: 0.85, idealist: 0.55, research: 0.75, spirit: 0.35, seminar: 0.55 },
  provenance: {},
};

function listed(id: string): ListedSchool {
  return { id, name: `School ${id}`, fit: 0.8, tier: "target", university: UNIVERSITY };
}

describe("UniversityModal focus handling", () => {
  it("moves focus into the dialog when it opens", () => {
    render(<UniversityModal name="MIT" university={UNIVERSITY} onClose={vi.fn()} />);

    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
  });

  it("keeps Tab inside the dialog", () => {
    render(<UniversityModal name="MIT" university={UNIVERSITY} onClose={vi.fn()} />);
    const close = screen.getByRole("button", { name: "Close" });
    close.focus();

    // Close is the only focusable control in this modal, so it is both edges:
    // Tab and Shift+Tab must both land back on it rather than leave.
    fireEvent.keyDown(close, { key: "Tab" });
    expect(document.activeElement).toBe(close);

    fireEvent.keyDown(close, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(close);
  });

  it("still closes on Escape", () => {
    const onClose = vi.fn();
    render(<UniversityModal name="MIT" university={UNIVERSITY} onClose={onClose} />);

    fireEvent.keyDown(document, { key: "Escape" });

    expect(onClose).toHaveBeenCalledOnce();
  });

  it("returns focus to the control that opened it", () => {
    function Harness({ open }: { open: boolean }) {
      return (
        <>
          <button type="button">Open MIT</button>
          {open && <UniversityModal name="MIT" university={UNIVERSITY} onClose={vi.fn()} />}
        </>
      );
    }

    const { rerender } = render(<Harness open={false} />);
    const opener = screen.getByRole("button", { name: "Open MIT" });
    opener.focus();

    rerender(<Harness open />);
    rerender(<Harness open={false} />);

    expect(document.activeElement).toBe(opener);
  });
});

describe("CompareTray dialog focus handling", () => {
  /** `compare` is session state, never persisted, so it is seeded the way the
   *  real UI seeds it: a component calling addToCompare from a click. */
  function AddToCompare({ school }: { school: ListedSchool }) {
    const { addToCompare } = useProfileStore();
    return (
      <button type="button" onClick={() => addToCompare(school)}>
        Add {school.id}
      </button>
    );
  }

  function openComparison() {
    render(
      <ProfileProvider>
        <AddToCompare school={listed("a")} />
        <CompareTray />
      </ProfileProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Add a" }));
    const compare = screen.getByRole("button", { name: "Compare" });
    // jsdom's click does not move focus the way a real one does, and "focus
    // goes back where it came from" is exactly what is under test here.
    compare.focus();
    fireEvent.click(compare);
  }

  it("shows no tray until something is being compared", () => {
    render(
      <ProfileProvider>
        <CompareTray />
      </ProfileProvider>,
    );

    expect(screen.queryByRole("button", { name: "Compare" })).toBeNull();
  });

  it("moves focus into the comparison when it opens", () => {
    openComparison();

    expect(screen.getByRole("dialog").contains(document.activeElement)).toBe(true);
  });

  it("closes the comparison on Escape", () => {
    openComparison();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("returns focus to the Compare button that opened it", () => {
    openComparison();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Compare" }));
  });
});
