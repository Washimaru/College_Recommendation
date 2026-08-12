"use client";

import { useState } from "react";

import { CompareTable } from "@/components/CompareTable";
import { COMPARE_LIMIT, useProfileStore } from "@/lib/profileStore";
import { useFocusTrap } from "@/lib/useFocusTrap";

/** Split out so the trap mounts and unmounts with the dialog itself: a hook
 *  inside CompareTray would run whether or not the dialog is open. */
function CompareDialog({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  const dialogRef = useFocusTrap<HTMLDivElement>(onClose);

  return (
    <div className="modal-back" role="dialog" aria-modal="true" aria-label="Compare schools"
         onClick={onClose}>
      <div className="modal" ref={dialogRef} style={{ maxWidth: 980 }}
           onClick={(e) => e.stopPropagation()}>
        <div className="card-head">
          <h2 style={{ marginBottom: 2 }}>Side by side</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Close">✕</button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function CompareTray() {
  const { compare, removeFromCompare } = useProfileStore();
  const [open, setOpen] = useState(false);

  if (compare.length === 0) return null;

  return (
    <>
      <div className="tray">
        <span className="muted" style={{ fontSize: 13 }}>
          Comparing {compare.length}/{COMPARE_LIMIT}
        </span>
        {compare.map((s) => (
          <button key={s.id} type="button" className="chip on" onClick={() => removeFromCompare(s.id)}>
            {s.name} ✕
          </button>
        ))}
        <button type="button" className="btn sm" onClick={() => setOpen(true)}>
          Compare
        </button>
      </div>

      {open && (
        <CompareDialog onClose={() => setOpen(false)}>
          <CompareTable schools={compare} />
        </CompareDialog>
      )}
    </>
  );
}
