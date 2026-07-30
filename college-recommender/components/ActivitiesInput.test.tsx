import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ActivitiesInput } from "./ActivitiesInput";
import type { Activity } from "@/lib/contract";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const LISTED: Activity[] = [
  { name: "FIRST Robotics", kind: "competition", subjects: ["Engineering"] },
  { name: "Science Bowl", kind: "competition", subjects: [] },
];

describe("ActivitiesInput", () => {
  it("shows what was recognised", () => {
    render(<ActivitiesInput activities={LISTED} onChange={() => {}} />);

    expect(screen.getByText(/recognised as/i).textContent).toContain("Engineering");
  });

  it("says so when nothing was recognised, rather than failing silently", () => {
    render(<ActivitiesInput activities={LISTED} onChange={() => {}} />);

    expect(screen.getByText(/not recognised/i)).toBeTruthy();
  });

  it("offers an explanation field for an unrecognised activity", () => {
    render(<ActivitiesInput activities={LISTED} onChange={() => {}} />);

    expect(screen.getByLabelText(/explain Science Bowl/i)).toBeTruthy();
  });
});
