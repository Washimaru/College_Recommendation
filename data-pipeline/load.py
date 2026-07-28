"""Load generated universities into Postgres. Reads DATABASE_URL from the env."""
from __future__ import annotations

import argparse
import json
import os
import sys

from generate import generate_universities


def load_universities(rows: list[dict], url: str) -> int:
    import psycopg
    from psycopg.types.json import Json

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            for r in rows:
                cur.execute(
                    """
                    INSERT INTO universities (
                        id, name, avg_gpa, avg_sat, acceptance_rate,
                        tuition, size, location, majors
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        avg_gpa = EXCLUDED.avg_gpa,
                        avg_sat = EXCLUDED.avg_sat,
                        acceptance_rate = EXCLUDED.acceptance_rate,
                        tuition = EXCLUDED.tuition,
                        size = EXCLUDED.size,
                        location = EXCLUDED.location,
                        majors = EXCLUDED.majors
                    """,
                    (r["id"], r["name"], r["avg_gpa"], r["avg_sat"], r["acceptance_rate"],
                     r["tuition"], r["size"], r["location"], Json(r["majors"])),
                )
        conn.commit()
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load universities into Postgres.")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--file", type=str, default=None, help="load rows from a JSON file")
    args = parser.parse_args(argv)

    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.stderr.write("DATABASE_URL is not set\n")
        return 2

    if args.file:
        with open(args.file) as fh:
            rows = json.load(fh)
    else:
        rows = generate_universities(args.count, args.seed)

    n = load_universities(rows, url)
    sys.stderr.write(f"loaded {n} universities\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
