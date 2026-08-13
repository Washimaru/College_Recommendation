import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProfileProvider } from "@/lib/profileStore";
import { ProfileForm } from "./ProfileForm";

/**
 * Where a student lives changes what a public university costs them, and the
 * net price in this catalog is the federal average for in-state students. The
 * question is optional: a student who skips it must send exactly what they
 * sent before, not an empty string the services would have to interpret.
 */

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

function mount() {
  return render(
    <ProfileProvider>
      <ProfileForm />
    </ProfileProvider>,
  );
}

function stubRecommend() {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ results: [], confidence: 0.9, stop_reason: "R2_confident", trace: [] }),
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function submittedProfile(fetchMock: ReturnType<typeof stubRecommend>) {
  fireEvent.click(screen.getByRole("button", { name: /show my matches/i }));
  await screen.findByRole("button", { name: /show my matches/i });
  const [, init] = fetchMock.mock.calls[0];
  return JSON.parse(init.body as string).profile;
}

describe("home state", () => {
  it("is offered as an optional question", () => {
    mount();

    expect(screen.getByLabelText(/home state/i)).toBeTruthy();
  });

  it("says why it is being asked", () => {
    mount();

    expect(screen.getByText(/in-state/i)).toBeTruthy();
  });

  it("is sent when the student picks one", async () => {
    const fetchMock = stubRecommend();
    mount();

    fireEvent.change(screen.getByLabelText(/home state/i), { target: { value: "MI" } });
    const profile = await submittedProfile(fetchMock);

    expect(profile.preferences.home_state).toBe("MI");
  });

  it("is omitted entirely when left blank, not sent as an empty string", async () => {
    const fetchMock = stubRecommend();
    mount();

    const profile = await submittedProfile(fetchMock);

    expect("home_state" in profile.preferences).toBe(false);
  });

  it("survives a reload, like the rest of the profile", () => {
    mount();
    fireEvent.change(screen.getByLabelText(/home state/i), { target: { value: "TX" } });
    cleanup();

    mount();

    expect((screen.getByLabelText(/home state/i) as HTMLSelectElement).value).toBe("TX");
  });
});
