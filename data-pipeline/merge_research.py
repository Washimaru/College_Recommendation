"""Fold researched faculty/research entries into `sources/school_details.json`.

Research arrives as one file per batch under `sources/research/batch-NN.json`, so
batches can run independently without contending for a single file.

The rules this enforces are the point of the script, not incidental:

- **Every entry must carry a source.** A claim about a named professor is a claim
  about a real, identifiable person; without a URL it is unverifiable and does
  not go in.
- **A school with nothing verifiable gets no section.** Empty strings, "none
  found", "N/A" and friends are dropped rather than stored, because absent
  sections simply do not render, while a hedged one would read as fact.
- **Existing entries win.** Re-running a batch must not overwrite hand-checked
  data with a later, weaker pass.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Values that mean "we found nothing" and must never be stored as if they were
# findings.
_EMPTY_MARKERS = {
    "",
    "n/a",
    "na",
    "none",
    "none found",
    "not found",
    "unknown",
    "tbd",
    "null",
}

MERGEABLE_SECTIONS = ("faculty", "research")


def is_empty(value: Any) -> bool:
    """True when a value carries no information worth storing."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in _EMPTY_MARKERS
    if isinstance(value, (list, tuple)):
        return all(is_empty(v) for v in value)
    if isinstance(value, dict):
        return all(is_empty(v) for v in value.values())
    return False


def clean_entry(entry: dict) -> dict | None:
    """Keep only sections that say something and are sourced.

    Returns None when nothing survives — the school then keeps no section at all,
    which is the honest outcome for a school we could not verify.
    """
    src = entry.get("src") or []
    if isinstance(src, str):
        src = [src]
    src = [s for s in src if isinstance(s, str) and s.startswith("http")]

    kept: dict[str, Any] = {}
    for section in MERGEABLE_SECTIONS:
        value = entry.get(section)
        if not is_empty(value):
            kept[section] = value

    if not kept:
        return None
    if not src:
        # Unsourced claims about named people do not go in, however plausible.
        return None

    kept["src"] = src
    if entry.get("_retrieved"):
        kept["_retrieved"] = entry["_retrieved"]
    return kept


def merge(details: dict, batch: dict) -> tuple[dict, dict[str, int]]:
    """Fold one batch into the details map. Existing sections are not overwritten."""
    stats = {"added": 0, "skipped_empty": 0, "skipped_existing": 0, "new_schools": 0}

    for school_id, raw in batch.items():
        cleaned = clean_entry(raw)
        if cleaned is None:
            stats["skipped_empty"] += 1
            continue

        current = details.get(school_id)
        if current is None:
            details[school_id] = {k: v for k, v in cleaned.items()}
            stats["new_schools"] += 1
            stats["added"] += 1
            continue

        wrote = False
        for section in MERGEABLE_SECTIONS:
            if section not in cleaned:
                continue
            if not is_empty(current.get(section)):
                stats["skipped_existing"] += 1
                continue
            current[section] = cleaned[section]
            wrote = True

        if wrote:
            existing_src = current.get("src") or []
            if isinstance(existing_src, str):
                existing_src = [existing_src]
            merged_src = list(dict.fromkeys([*existing_src, *cleaned["src"]]))
            current["src"] = merged_src
            stats["added"] += 1

    return details, stats


def main() -> None:
    root = Path(__file__).parent
    details_path = root / "sources" / "school_details.json"
    details = json.loads(details_path.read_text(encoding="utf-8"))

    totals = {"added": 0, "skipped_empty": 0, "skipped_existing": 0, "new_schools": 0}
    batch_files = sorted((root / "sources" / "research").glob("batch-*.json"))
    if not batch_files:
        print("no batch files found in sources/research/")
        return

    for path in batch_files:
        batch = json.loads(path.read_text(encoding="utf-8"))
        details, stats = merge(details, batch)
        print(f"{path.name}: +{stats['added']} "
              f"(empty {stats['skipped_empty']}, kept-existing {stats['skipped_existing']})")
        for key in totals:
            totals[key] += stats[key]

    details_path.write_text(
        json.dumps(details, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    faculty = sum(1 for d in details.values() if not is_empty(d.get("faculty")))
    research = sum(1 for d in details.values() if not is_empty(d.get("research")))
    print(f"\nmerged {totals['added']} entries from {len(batch_files)} batches")
    print(f"school_details.json now: {len(details)} schools, "
          f"{faculty} with faculty, {research} with research")


if __name__ == "__main__":
    main()
