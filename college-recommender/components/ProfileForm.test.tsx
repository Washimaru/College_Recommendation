import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ProfileProvider } from "@/lib/profileStore";
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
});
