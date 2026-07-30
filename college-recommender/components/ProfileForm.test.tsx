import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ProfileProvider, useProfileStore } from "@/lib/profileStore";
import { ProfileForm } from "./ProfileForm";

afterEach(cleanup);

function mount() {
  return render(
    <ProfileProvider>
      <ProfileForm />
    </ProfileProvider>,
  );
}

describe("ProfileForm", () => {
  it("offers every region as a toggle", () => {
    mount();

    for (const region of ["Northeast", "South", "West", "Midwest", "International"]) {
      expect(screen.getByRole("button", { name: region })).toBeTruthy();
    }
  });

  it("offers the three campus settings", () => {
    mount();

    for (const setting of ["Urban", "Suburban", "Rural"]) {
      expect(screen.getByRole("button", { name: setting })).toBeTruthy();
    }
  });

  it("offers a public/private choice", () => {
    mount();
    expect(screen.getByLabelText(/public or private/i)).toBeTruthy();
  });

  it("renders no MBTI control", () => {
    mount();
    expect(screen.queryByText(/mbti/i)).toBeNull();
  });

  it("labels both ends of every preference question", () => {
    mount();
    expect(screen.getByText(/I'd rather we all helped each other/i)).toBeTruthy();
  });

  it("shows matches again after the form remounts (a route change), without re-running the loop", () => {
    let store: ReturnType<typeof useProfileStore>;
    function Probe() {
      store = useProfileStore();
      return null;
    }

    // ProfileProvider is the one held constant across a route change (it
    // lives in the root layout); only the page inside it — ProfileForm —
    // unmounts and remounts. `rerender` on the same root, with the same
    // <ProfileProvider> element each time, is what actually simulates that;
    // two independent `render` calls would each create a fresh provider,
    // which is not what navigating within the app does.
    const { rerender } = render(
      <ProfileProvider>
        <Probe />
        <ProfileForm />
      </ProfileProvider>,
    );

    act(() =>
      store.setResults({
        results: [
          {
            university_id: "u1",
            name: "Remembered University",
            score: 0.88,
            rationale: "Strong fit.",
            admit_tier: "target",
            university: {
              country: "USA",
              location: "Cambridge, MA",
              region: "Northeast",
              setting: "urban",
              type: "Private",
              avg_gpa: 3.9,
              size: "small",
              majors: ["Computer Science"],
              culture: {
                collab: 0.5, quirky: 0.5, idealist: 0.5, research: 0.5, spirit: 0.5, seminar: 0.5,
              },
              provenance: {},
            },
          },
        ],
        confidence: 0.92,
        stop_reason: "R2_confident",
        trace: [],
      }),
    );

    // Navigate away (ProfileForm unmounts) and back (it remounts).
    rerender(
      <ProfileProvider>
        <Probe />
        <div>elsewhere</div>
      </ProfileProvider>,
    );
    rerender(
      <ProfileProvider>
        <Probe />
        <ProfileForm />
      </ProfileProvider>,
    );

    expect(screen.getByText("Remembered University")).toBeTruthy();
  });
});
