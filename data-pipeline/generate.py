"""Synthetic university generator with realistic, correlated distributions.

Randomness is allowed here (this is the data pipeline, not scoring). Output is
deterministic for a given seed so tests and smoke runs are reproducible.
"""
from __future__ import annotations

import argparse
import json
import random
import sys

LOCATIONS = ["CA", "NY", "MA", "TX", "IL", "WA", "PA", "GA", "OH", "MI", "NC", "FL"]
SIZES = ["small", "medium", "large"]
MAJOR_POOL = [
    "Computer Science", "Mathematics", "Physics", "Biology", "Chemistry",
    "Economics", "Business", "Engineering", "English", "History",
    "Psychology", "Data Science", "Political Science", "Art", "Nursing",
]
_ADJ = ["North", "South", "East", "West", "Lake", "Cedar", "Summit", "Bay",
        "River", "Fair", "Green", "Vantage", "Port", "Ash", "Stone", "Clear"]
_NOUN = ["University", "College", "Institute", "State", "Polytechnic", "Tech"]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def generate_universities(count: int = 100, seed: int = 42) -> list[dict]:
    """Return `count` synthetic universities. More selective schools (lower
    acceptance_rate) trend toward higher avg_sat/avg_gpa and higher tuition."""
    rng = random.Random(seed)
    seen_names: set[str] = set()
    unis: list[dict] = []
    for i in range(count):
        acceptance = round(rng.uniform(0.05, 0.85), 3)
        selectivity = 1.0 - acceptance
        avg_sat = int(round((1000 + selectivity * 560 + rng.gauss(0, 30)) / 10.0) * 10)
        avg_sat = int(_clamp(avg_sat, 900, 1580))
        avg_gpa = round(_clamp(2.8 + selectivity * 1.1 + rng.gauss(0, 0.08), 2.0, 4.0), 2)
        size = rng.choice(SIZES)
        tuition = round(_clamp(18000 + selectivity * 40000 + rng.gauss(0, 4000), 8000, 65000), 2)

        name = f"{rng.choice(_ADJ)} {rng.choice(_NOUN)}"
        while name in seen_names:
            name = f"{rng.choice(_ADJ)}{rng.choice(_ADJ)} {rng.choice(_NOUN)}"
        seen_names.add(name)

        k = rng.randint(2, 4)
        majors = sorted(rng.sample(MAJOR_POOL, k))
        unis.append({
            "id": f"u{i:04d}",
            "name": name,
            "avg_gpa": avg_gpa,
            "avg_sat": avg_sat,
            "acceptance_rate": acceptance,
            "tuition": tuition,
            "size": size,
            "location": rng.choice(LOCATIONS),
            "majors": majors,
        })
    return unis


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate synthetic universities.")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=str, default="-", help="output path or - for stdout")
    args = parser.parse_args(argv)
    data = generate_universities(args.count, args.seed)
    payload = json.dumps(data, indent=2)
    if args.out == "-":
        sys.stdout.write(payload + "\n")
    else:
        with open(args.out, "w") as fh:
            fh.write(payload)
        sys.stderr.write(f"wrote {len(data)} universities to {args.out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
