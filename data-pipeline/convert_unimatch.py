"""Tier-1 converter: UniMatch editorial dataset (JavaScript) -> canonical JSON.

One-time-ish conversion, re-runnable. The source files are JavaScript, so this
is deliberately a targeted extractor rather than a JS parser.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def _records(js_text: str):
    """Yield each brace-balanced `{n:"..." ...}` record. Brace counting rather
    than a regex because records contain a nested `v:{...}` object."""
    for match in re.finditer(r'\{n:"', js_text):
        depth = 0
        for i in range(match.start(), len(js_text)):
            if js_text[i] == "{":
                depth += 1
            elif js_text[i] == "}":
                depth -= 1
                if depth == 0:
                    yield js_text[match.start() : i + 1]
                    break


def _text(record: str, key: str) -> str | None:
    found = re.search(rf'\b{key}:"([^"]*)"', record)
    return found.group(1) if found else None


def _number(record: str, key: str) -> float | None:
    found = re.search(rf"\b{key}:\s*(-?\d*\.?\d+)", record)
    return float(found.group(1)) if found else None


# The six bipolar culture axes. Order is fixed and shared with the scorer.
CULTURE_KEYS = ("collab", "quirky", "idealist", "research", "spirit", "seminar")


def _culture(record: str) -> dict[str, float]:
    found = re.search(r"\bv:\s*\{([^}]*)\}", record)
    if not found:
        return {}
    body = found.group(1)
    values = {}
    for key in CULTURE_KEYS:
        axis = re.search(rf"\b{key}:\s*(-?\d*\.?\d+)", body)
        if axis:
            values[key] = float(axis.group(1))
    return values


def _strings(record: str, key: str) -> list[str]:
    found = re.search(rf"\b{key}:\s*\[([^\]]*)\]", record)
    return re.findall(r'"([^"]*)"', found.group(1)) if found else []


def parse_universities(js_text: str) -> list[dict]:
    """Extract university records from the text of a UniMatch data*.js file."""
    out: list[dict] = []
    for record in _records(js_text):
        size = _number(record, "size")
        net = _number(record, "net")
        out.append(
            {
                "name": _text(record, "n"),
                "location": _text(record, "loc"),
                "country": _text(record, "ctry"),
                "region": _text(record, "region"),
                "type": _text(record, "type"),
                "setting": _text(record, "setting"),
                "enrollment_editorial": int(size) if size is not None else None,
                "net_price": int(net) if net is not None else None,
                "avg_gpa": _number(record, "gpa"),
                "majors": _strings(record, "strengths"),
                "culture": _culture(record),
            }
        )
    return out


def slugify(name: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-")


def convert(source_dir: Path) -> list[dict]:
    """Parse every `data*.js` in `source_dir` into canonical records.

    Files are read in sorted order (data.js, data2.js, ...) so the output is
    deterministic. Ids are slugs; a collision gets a numeric suffix rather than
    silently overwriting.
    """
    records: list[dict] = []
    for path in sorted(source_dir.glob("data*.js")):
        records.extend(parse_universities(path.read_text(encoding="utf-8", errors="replace")))

    seen: dict[str, int] = {}
    for record in records:
        base = slugify(record["name"] or "")
        seen[base] = seen.get(base, 0) + 1
        record["id"] = base if seen[base] == 1 else f"{base}-{seen[base]}"
    return records


def write_catalog(records: list[dict], out_path: Path) -> None:
    """Write records as JSON, sorted by id so output is byte-stable."""
    ordered = sorted(records, key=lambda r: r["id"])
    out_path.write_text(
        json.dumps(ordered, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Convert the UniMatch JS dataset to JSON.")
    parser.add_argument("--source", required=True, help="directory holding data*.js")
    parser.add_argument("--out", default="sources/unimatch_364.json")
    args = parser.parse_args(argv)

    records = convert(Path(args.source).expanduser())
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_catalog(records, out_path)
    sys.stderr.write(f"wrote {len(records)} universities to {out_path}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
