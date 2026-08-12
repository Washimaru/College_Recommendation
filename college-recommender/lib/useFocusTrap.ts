"use client";

import { useEffect, useRef } from "react";

/**
 * Keeps keyboard focus inside an open dialog, and gives it back on close.
 *
 * `aria-modal="true"` tells assistive technology a dialog is modal; it does not
 * make it so. Without this, Tab walks straight out of the dialog into the page
 * behind it - which is still scrollable and still clickable - and closing the
 * dialog drops focus to the top of the document rather than to whatever opened
 * it.
 *
 * Escape lives here too, so both modals close the same way rather than one of
 * them growing its own listener.
 */
const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(", ");

export function useFocusTrap<T extends HTMLElement>(onClose: () => void) {
  const ref = useRef<T>(null);

  // Deliberately two effects. Moving focus in, and handing it back, must happen
  // once per open and close, so that effect takes no dependencies. The key
  // handler has to see the current `onClose` - usually an inline arrow - so it
  // re-subscribes per render. Combined, the focus move would re-run on every
  // render and yank focus back to the first control mid-interaction.
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;

    const previouslyFocused = document.activeElement as HTMLElement | null;
    const first = dialog.querySelector<HTMLElement>(FOCUSABLE);
    if (first) {
      first.focus();
    } else {
      // Nothing focusable inside, but focus still must not stay outside.
      dialog.tabIndex = -1;
      dialog.focus();
    }

    return () => {
      // Give focus back unless something else has deliberately claimed it.
      // Testing `dialog.contains(activeElement)` alone is not enough: by the
      // time this cleanup runs the dialog may already be detached, which drops
      // focus to <body> - the very case that needs restoring.
      const active = document.activeElement;
      const claimedElsewhere =
        active !== null && active !== document.body && !dialog.contains(active);
      if (previouslyFocused?.isConnected && !claimedElsewhere) {
        previouslyFocused.focus();
      }
    };
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab") return;

      const dialog = ref.current;
      if (!dialog) return;

      // Re-read on every keystroke: a dialog's contents change as sections
      // render, so a list captured when it opened would go stale.
      const items = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (items.length === 0) {
        event.preventDefault();
        return;
      }

      const edge = event.shiftKey ? items[0] : items[items.length - 1];
      if (document.activeElement !== edge) return;

      event.preventDefault();
      (event.shiftKey ? items[items.length - 1] : items[0]).focus();
    };

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return ref;
}
