"""Load the built university catalog into Postgres. Reads DATABASE_URL from the env.

The catalog comes from build_catalog.py; the synthetic generator is no longer
on this path now that the catalog holds real institutions."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def load_universities(rows: list[dict], url: str) -> int:
    import psycopg
    from psycopg.types.json import Json

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            for r in rows:
                cur.execute(
                    """
                    INSERT INTO universities (
                        id, unitid, name, country, location, avg_gpa, avg_sat,
                        acceptance_rate, net_price, sticker_tuition, enrollment,
                        size, majors, culture, provenance
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        unitid = EXCLUDED.unitid,
                        name = EXCLUDED.name,
                        country = EXCLUDED.country,
                        location = EXCLUDED.location,
                        avg_gpa = EXCLUDED.avg_gpa,
                        avg_sat = EXCLUDED.avg_sat,
                        acceptance_rate = EXCLUDED.acceptance_rate,
                        net_price = EXCLUDED.net_price,
                        sticker_tuition = EXCLUDED.sticker_tuition,
                        enrollment = EXCLUDED.enrollment,
                        size = EXCLUDED.size,
                        majors = EXCLUDED.majors,
                        culture = EXCLUDED.culture,
                        provenance = EXCLUDED.provenance
                    """,
                    (r["id"], r.get("unitid"), r["name"], r["country"], r["location"],
                     r["avg_gpa"], r.get("avg_sat"), r.get("acceptance_rate"),
                     r.get("net_price"), r.get("sticker_tuition"), r.get("enrollment"),
                     r["size"], Json(r["majors"]), Json(r["culture"]),
                     Json(r.get("provenance", {}))),
                )
        conn.commit()
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load universities into Postgres.")
    parser.add_argument(
        "--file",
        default="out/universities.json",
        help="catalog JSON produced by build_catalog.py",
    )
    args = parser.parse_args(argv)

    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.stderr.write("DATABASE_URL is not set\n")
        return 2

    path = Path(args.file)
    if not path.exists():
        sys.stderr.write(f"{path} not found; run build_catalog.py first\n")
        return 2
    rows = json.loads(path.read_text(encoding="utf-8"))

    n = load_universities(rows, url)
    sys.stderr.write(f"loaded {n} universities\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
