import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { UniversitySummary } from "@/lib/contract";
import { UniversityModal } from "./UniversityModal";

/**
 * Contract v7: what a school costs a resident, and what it actually teaches.
 *
 * The out-of-state figure alone misstates a public university badly — Michigan
 * is $17,736 in state and $60,946 out — and `majors` can never support "does
 * not offer X", because it lists strengths. `programs` is federal data on
 * degrees actually awarded, so it can.
 */

afterEach(cleanup);

const BASE: UniversitySummary = {
  country: "USA",
  location: "Ann Arbor, MI",
  region: "Midwest",
  setting: "suburban",
  type: "Public",
  avg_gpa: 3.8,
  size: "large",
  majors: ["Engineering"],
  culture: { collab: 0.5, quirky: 0.5, idealist: 0.5, research: 0.5, spirit: 0.5, seminar: 0.5 },
  provenance: {},
};

function show(overrides: Partial<UniversitySummary>) {
  render(
    <UniversityModal name="Michigan" university={{ ...BASE, ...overrides }} onClose={vi.fn()} />,
  );
}

describe("tuition", () => {
  it("shows both prices when they differ", () => {
    show({
      tuition_in_state: 17736,
      sticker_tuition: 60946,
      provenance: { tuition_in_state: "observed", sticker_tuition: "observed" },
    });

    expect(screen.getByText("$17,736")).toBeTruthy();
    expect(screen.getByText("$60,946")).toBeTruthy();
    expect(screen.getByText(/in state/i)).toBeTruthy();
  });

  it("shows one price when in-state and out-of-state are the same", () => {
    show({
      type: "Private",
      tuition_in_state: 62396,
      sticker_tuition: 62396,
      provenance: { tuition_in_state: "observed", sticker_tuition: "observed" },
    });

    expect(screen.getAllByText("$62,396")).toHaveLength(1);
    expect(screen.queryByText(/in state/i)).toBeNull();
  });

  it("does not invent an in-state price from the out-of-state one", () => {
    show({ sticker_tuition: 60946, provenance: { sticker_tuition: "observed" } });

    expect(screen.queryByText(/in state/i)).toBeNull();
    expect(screen.getByText("$60,946")).toBeTruthy();
  });
});

describe("programs", () => {
  it("lists what the school actually awards degrees in", () => {
    show({
      programs: [
        { name: "Engineering", share: 0.27 },
        { name: "Computer & Information Sciences", share: 0.16 },
      ],
    });

    // "Engineering" also appears in the editorial strengths list above, which
    // is exactly the pair this feature has to keep distinguishable.
    expect(screen.getByText("Engineering · 27%")).toBeTruthy();
    expect(screen.getByText("Computer & Information Sciences · 16%")).toBeTruthy();
  });

  it("says nothing at all when the data is missing", () => {
    show({ programs: null });

    expect(screen.queryByText(/degrees awarded/i)).toBeNull();
  });

  it("says so plainly when a school awards none of these", () => {
    show({ programs: [] });

    expect(screen.getByText(/no degrees/i)).toBeTruthy();
  });

  it("credits the source, since this is the field that licenses absence claims", () => {
    show({ programs: [{ name: "Engineering", share: 0.27 }] });

    expect(screen.getByText(/federal/i)).toBeTruthy();
  });
});

describe("out-of-state warning", () => {
  const PUBLIC_MI = {
    ...BASE,
    state: "MI",
    net_price: 13138,
    tuition_in_state: 17736,
    sticker_tuition: 60946,
    provenance: { net_price: "observed" as const },
  };

  it("warns a student from another state that the net price is not theirs", () => {
    render(
      <UniversityModal
        name="Michigan"
        university={PUBLIC_MI}
        homeState="TX"
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText(/in-state students/i)).toBeTruthy();
  });

  it("says nothing to a resident", () => {
    render(
      <UniversityModal
        name="Michigan"
        university={PUBLIC_MI}
        homeState="MI"
        onClose={vi.fn()}
      />,
    );

    expect(screen.queryByText(/in-state students/i)).toBeNull();
  });

  it("says nothing when the student did not give a state", () => {
    render(<UniversityModal name="Michigan" university={PUBLIC_MI} onClose={vi.fn()} />);

    expect(screen.queryByText(/in-state students/i)).toBeNull();
  });

  it("says nothing at a private school, where the two prices are the same", () => {
    render(
      <UniversityModal
        name="MIT"
        university={{
          ...BASE,
          type: "Private",
          state: "MA",
          net_price: 20111,
          tuition_in_state: 62396,
          sticker_tuition: 62396,
        }}
        homeState="TX"
        onClose={vi.fn()}
      />,
    );

    expect(screen.queryByText(/in-state students/i)).toBeNull();
  });
});

describe("professors", () => {
  const CHOMSKY = {
    name: "Noam Chomsky",
    known_for: "American linguist and cognitive scientist",
    fields: ["linguist", "philosopher"],
    status: "current" as const,
    prominence: 178,
    source: "wikipedia" as const,
    source_url: "https://en.wikipedia.org/wiki/Noam_Chomsky",
  };
  const ADAMS = {
    name: "Ansel Adams",
    known_for: "American photographer",
    fields: ["photographer"],
    status: "historical" as const,
    prominence: 84,
    source: "wikipedia" as const,
    source_url: "https://en.wikipedia.org/wiki/Ansel_Adams",
  };

  it("names the professors and what they are known for", () => {
    show({ notable_faculty: [CHOMSKY] });

    expect(screen.getByText("Noam Chomsky")).toBeTruthy();
    expect(screen.getByText(/American linguist and cognitive scientist/)).toBeTruthy();
  });

  it("links each one to the source, so a reader can check", () => {
    show({ notable_faculty: [CHOMSKY] });

    const link = screen.getByRole("link", { name: /Noam Chomsky/ });
    expect(link.getAttribute("href")).toBe("https://en.wikipedia.org/wiki/Noam_Chomsky");
  });

  it("never implies a historical professor still teaches", () => {
    show({ notable_faculty: [ADAMS] });

    expect(screen.getByText(/no longer teaching|formerly|historical/i)).toBeTruthy();
  });

  it("says nothing at all when nobody searched", () => {
    show({ notable_faculty: null });

    expect(screen.queryByText(/professors/i)).toBeNull();
  });

  it("says so plainly when the search found nobody", () => {
    show({ notable_faculty: [] });

    expect(screen.getByText(/didn.t find|none/i)).toBeTruthy();
  });

  it("credits the source rather than presenting it as our own research", () => {
    show({ notable_faculty: [CHOMSKY] });

    expect(screen.getByText(/Wikipedia/i)).toBeTruthy();
  });
});

describe("choosing a field of study", () => {
  const FACULTY = [
    { name: "Nora Physicist", known_for: "American physicist", fields: ["physicist"],
      status: "current" as const, prominence: 40, source: "wikipedia" as const,
      source_url: "https://en.wikipedia.org/wiki/Nora" },
    { name: "Eve Economist", known_for: "American economist", fields: ["economist"],
      status: "current" as const, prominence: 30, source: "wikipedia" as const,
      source_url: "https://en.wikipedia.org/wiki/Eve" },
  ];
  const PROGRAMS = [
    { name: "Physical Sciences", share: 0.2 },
    { name: "Social Sciences", share: 0.15 },
    { name: "Agriculture", share: 0.05 },
  ];

  function withFaculty() {
    show({ notable_faculty: FACULTY, programs: PROGRAMS });
  }

  it("offers the fields this school teaches and has professors for", () => {
    withFaculty();

    expect(screen.getByRole("button", { name: /Physical Sciences/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /Social Sciences/ })).toBeTruthy();
  });

  it("does not offer a field with no professors behind it", () => {
    withFaculty();

    expect(screen.queryByRole("button", { name: /^Agriculture/ })).toBeNull();
  });

  it("shows everyone until a field is chosen", () => {
    withFaculty();

    expect(screen.getByText("Nora Physicist")).toBeTruthy();
    expect(screen.getByText("Eve Economist")).toBeTruthy();
  });

  it("narrows to that field's professors when one is chosen", () => {
    withFaculty();

    fireEvent.click(screen.getByRole("button", { name: /Physical Sciences/ }));

    expect(screen.getByText("Nora Physicist")).toBeTruthy();
    expect(screen.queryByText("Eve Economist")).toBeNull();
  });

  it("can be cleared back to everyone", () => {
    withFaculty();

    fireEvent.click(screen.getByRole("button", { name: /Physical Sciences/ }));
    fireEvent.click(screen.getByRole("button", { name: /All fields/ }));

    expect(screen.getByText("Eve Economist")).toBeTruthy();
  });

  it("offers no chooser when the school has no degree data to choose from", () => {
    show({ notable_faculty: FACULTY, programs: null });

    expect(screen.queryByRole("button", { name: /All fields/ })).toBeNull();
    expect(screen.getByText("Nora Physicist")).toBeTruthy();
  });
});
