import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { MajorFinder } from "./MajorFinder";

afterEach(cleanup);

describe("MajorFinder", () => {
  it("surfaces a catalog error instead of implying no school teaches any major", () => {
    render(
      <MajorFinder
        catalog={null}
        error="Couldn't load the catalog. Is the stack running?"
        onOpen={() => {}}
      />,
    );

    expect(screen.getByText(/couldn't load the catalog/i)).toBeTruthy();
  });

  it("explains why a major's schools are missing when the catalog failed, rather than nothing", () => {
    render(
      <MajorFinder
        catalog={null}
        error="Couldn't load the catalog. Is the stack running?"
        onOpen={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /recommend my majors/i }));

    expect(screen.getAllByText(/catalog service is unreachable/i).length).toBeGreaterThan(0);
  });

  it("shows no error notice when the catalog loaded fine", () => {
    render(<MajorFinder catalog={[]} error={null} onOpen={() => {}} />);

    expect(screen.queryByText(/couldn't load/i)).toBeNull();
  });
});
