import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
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

/** Stateful wrapper so an add/explain round trip is actually visible in the
 *  DOM, the way it is once ActivitiesInput sits inside ProfileForm. */
function Stateful({ initial = [] as Activity[] }) {
  const [activities, setActivities] = useState<Activity[]>(initial);
  return <ActivitiesInput activities={activities} onChange={setActivities} />;
}

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

  it("says it couldn't check, not that nothing was recognised, when the classifier is unreachable", async () => {
    vi.spyOn(global, "fetch").mockRejectedValue(new Error("network down"));

    render(<Stateful />);

    fireEvent.change(screen.getByLabelText(/what you did/i), { target: { value: "Chess club" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    expect(await screen.findByText(/couldn.t check/i)).toBeTruthy();
    expect(screen.queryByText(/not recognised/i)).toBeNull();
  });

  it("still adds the activity when the classifier is unreachable", async () => {
    vi.spyOn(global, "fetch").mockRejectedValue(new Error("network down"));

    render(<Stateful />);

    fireEvent.change(screen.getByLabelText(/what you did/i), { target: { value: "Chess club" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    expect(await screen.findByText("Chess club")).toBeTruthy();
  });

  it("does not invite the student to rewrite anything when the classifier is unreachable", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue(new Response(null, { status: 503 }));

    render(<Stateful />);

    fireEvent.change(screen.getByLabelText(/what you did/i), { target: { value: "Chess club" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    const notice = await screen.findByText(/couldn.t check/i);
    expect(notice.textContent?.toLowerCase()).not.toContain("tell us what you did");
  });
});
