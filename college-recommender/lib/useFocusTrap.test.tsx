import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useFocusTrap } from "./useFocusTrap";

/**
 * `aria-modal="true"` is a promise to assistive technology, not an enforced
 * trap: browsers still let Tab walk out of the dialog into the page behind it,
 * and nothing returns focus when the dialog closes. Both modals in this app
 * are reachable from all four routes, so a keyboard user who opened one used
 * to end up tabbing through a page they could no longer see.
 */

afterEach(cleanup);

function Dialog({ onClose, withFields = true }: { onClose: () => void; withFields?: boolean }) {
  const ref = useFocusTrap<HTMLDivElement>(onClose);
  return (
    <div ref={ref} role="dialog" aria-modal="true" aria-label="Test dialog">
      {withFields && (
        <>
          <button type="button">First</button>
          <input aria-label="Middle" />
          <button type="button">Last</button>
        </>
      )}
      {!withFields && <p>Nothing focusable here</p>}
    </div>
  );
}

function Harness({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <>
      <button type="button">Opener</button>
      {open && <Dialog onClose={onClose} />}
    </>
  );
}

describe("useFocusTrap", () => {
  it("moves focus into the dialog on open", () => {
    render(<Dialog onClose={vi.fn()} />);

    expect(document.activeElement).toBe(screen.getByRole("button", { name: "First" }));
  });

  it("focuses the dialog itself when it holds nothing focusable", () => {
    render(<Dialog onClose={vi.fn()} withFields={false} />);

    expect(document.activeElement).toBe(screen.getByRole("dialog"));
  });

  it("wraps Tab from the last control back to the first", () => {
    render(<Dialog onClose={vi.fn()} />);
    const last = screen.getByRole("button", { name: "Last" });
    last.focus();

    fireEvent.keyDown(last, { key: "Tab" });

    expect(document.activeElement).toBe(screen.getByRole("button", { name: "First" }));
  });

  it("wraps Shift+Tab from the first control round to the last", () => {
    render(<Dialog onClose={vi.fn()} />);
    const first = screen.getByRole("button", { name: "First" });
    first.focus();

    fireEvent.keyDown(first, { key: "Tab", shiftKey: true });

    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Last" }));
  });

  it("leaves Tab alone in the middle of the dialog", () => {
    render(<Dialog onClose={vi.fn()} />);
    const middle = screen.getByLabelText("Middle");
    middle.focus();

    fireEvent.keyDown(middle, { key: "Tab" });

    expect(document.activeElement).toBe(middle);
  });

  it("closes on Escape", () => {
    const onClose = vi.fn();
    render(<Dialog onClose={onClose} />);

    fireEvent.keyDown(document, { key: "Escape" });

    expect(onClose).toHaveBeenCalledOnce();
  });

  it("returns focus to whatever opened it", () => {
    const { rerender } = render(<Harness open={false} onClose={vi.fn()} />);
    const opener = screen.getByRole("button", { name: "Opener" });
    opener.focus();

    rerender(<Harness open onClose={vi.fn()} />);
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "First" }));

    rerender(<Harness open={false} onClose={vi.fn()} />);
    expect(document.activeElement).toBe(opener);
  });
});
