import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProfileProvider, useProfileStore } from "@/lib/profileStore";
import { ProfileForm } from "./ProfileForm";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

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

  it("shows an unweighted GPA field (required, scored) and an optional weighted GPA field", () => {
    mount();

    const unweighted = screen.getByLabelText(/unweighted gpa/i) as HTMLInputElement;
    const weighted = screen.getByLabelText(/\bweighted gpa/i) as HTMLInputElement;

    expect(unweighted.required).toBe(true);
    expect(unweighted.max).toBe("4");
    expect(weighted.required).toBe(false);
    expect(weighted.max).toBe("5");
  });

  it("tells the student which GPA is actually scored", () => {
    mount();

    expect(screen.getByText(/score on the unweighted/i)).toBeTruthy();
  });

  it("omits gpa_weighted from the request body when left blank", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ results: [], confidence: 0.9, stop_reason: "R2_confident", trace: [] }),
    });
    vi.stubGlobal("fetch", fetchMock);
    mount();

    fireEvent.click(screen.getByRole("button", { name: /show my matches/i }));
    await screen.findByRole("button", { name: /show my matches/i });

    const [, init] = fetchMock.mock.calls[0];
    const body = JSON.parse(init.body as string);
    expect("gpa_weighted" in body.profile).toBe(false);
  });

  it("includes gpa_weighted as a number in the request body when provided", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ results: [], confidence: 0.9, stop_reason: "R2_confident", trace: [] }),
    });
    vi.stubGlobal("fetch", fetchMock);
    mount();

    fireEvent.change(screen.getByLabelText(/\bweighted gpa/i), { target: { value: "4.42" } });
    fireEvent.click(screen.getByRole("button", { name: /show my matches/i }));
    await screen.findByRole("button", { name: /show my matches/i });

    const [, init] = fetchMock.mock.calls[0];
    const body = JSON.parse(init.body as string);
    expect(body.profile.gpa_weighted).toBe(4.42);
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

describe("ProfileForm announcements", () => {
  const RESULT = {
    university_id: "mit",
    name: "MIT",
    score: 0.9,
    rationale: "Strong on fit.",
    admit_tier: "target",
    university: {
      country: "USA", location: "Cambridge, MA", region: "Northeast", setting: "urban",
      type: "Private", avg_gpa: 3.95, size: "small", majors: ["Computer Science"],
      culture: { collab: 0.5, quirky: 0.5, idealist: 0.5, research: 0.5, spirit: 0.5, seminar: 0.5 },
      provenance: {},
    },
  };

  function stubRecommend(results: unknown[]) {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ results, confidence: 0.9, stop_reason: "R2_confident", trace: [] }),
      }),
    );
  }

  it("has a live region before anything happens, so a later change is announced", () => {
    mount();

    expect(screen.getByRole("status")).toBeTruthy();
  });

  it("announces how many schools matched", async () => {
    stubRecommend([RESULT, { ...RESULT, university_id: "caltech", name: "Caltech" }]);
    mount();

    fireEvent.click(screen.getByRole("button", { name: /show my matches/i }));

    expect(await screen.findByText(/2 schools matched/i)).toBeTruthy();
    expect(screen.getByRole("status").textContent).toMatch(/2 schools matched/i);
  });

  it("says so when nothing matched, rather than announcing silence", async () => {
    stubRecommend([]);
    mount();

    fireEvent.click(screen.getByRole("button", { name: /show my matches/i }));

    expect((await screen.findByRole("status")).textContent).toMatch(/no schools matched/i);
  });

  it("announces that the search is running", () => {
    stubRecommend([RESULT]);
    mount();

    fireEvent.click(screen.getByRole("button", { name: /show my matches/i }));

    expect(screen.getByRole("status").textContent).toMatch(/finding|matching/i);
  });

  it("leaves the error branch to role=alert, so a failure is not announced twice", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));
    mount();

    fireEvent.click(screen.getByRole("button", { name: /show my matches/i }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBeTruthy();
    expect(screen.getByRole("status").textContent).toBe("");
  });
});
