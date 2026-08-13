"""Load the built university catalog into Postgres. Reads DATABASE_URL from the env.

The catalog comes from build_catalog.py; the synthetic generator is no longer
on this path now that the catalog holds real institutions."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# A build that emits only a handful of records is broken, not a catalog that
# shrank. Pruning on that would empty the table.
MIN_SAFE_ROWS = 100


def rows_to_delete(existing_ids: set[str], catalog_ids: set[str]) -> set[str]:
    """Ids present in the database but no longer in the catalog.

    Raises if the catalog looks too small to trust, so a failed build cannot
    delete the live data.
    """
    if len(catalog_ids) < MIN_SAFE_ROWS:
        raise ValueError(
            f"refusing to prune: catalog has only {len(catalog_ids)} records, "
            f"expected at least {MIN_SAFE_ROWS}"
        )
    return existing_ids - catalog_ids


def load_universities(rows: list[dict], url: str) -> int:
    import psycopg
    from psycopg.types.json import Json

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            for r in rows:
                cur.execute(
                    """
                    INSERT INTO universities (
                        id, unitid, name, country, location, state, region, setting,
                        type, avg_gpa, avg_sat, acceptance_rate, net_price,
                        sticker_tuition, tuition_in_state, programs,
                        enrollment, size, majors, culture,
                        population, url, net_price_calculator_url, details,
                        provenance
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        unitid = EXCLUDED.unitid,
                        name = EXCLUDED.name,
                        country = EXCLUDED.country,
                        location = EXCLUDED.location,
                        state = EXCLUDED.state,
                        region = EXCLUDED.region,
                        setting = EXCLUDED.setting,
                        type = EXCLUDED.type,
                        avg_gpa = EXCLUDED.avg_gpa,
                        avg_sat = EXCLUDED.avg_sat,
                        acceptance_rate = EXCLUDED.acceptance_rate,
                        net_price = EXCLUDED.net_price,
                        sticker_tuition = EXCLUDED.sticker_tuition,
                        tuition_in_state = EXCLUDED.tuition_in_state,
                        programs = EXCLUDED.programs,
                        enrollment = EXCLUDED.enrollment,
                        size = EXCLUDED.size,
                        majors = EXCLUDED.majors,
                        culture = EXCLUDED.culture,
                        population = EXCLUDED.population,
                        url = EXCLUDED.url,
                        net_price_calculator_url = EXCLUDED.net_price_calculator_url,
                        details = EXCLUDED.details,
                        provenance = EXCLUDED.provenance
                    """,
                    (r["id"], r.get("unitid"), r["name"], r["country"], r["location"],
                     r.get("state"), r["region"], r["setting"], r["type"],
                     r["avg_gpa"], r.get("avg_sat"), r.get("acceptance_rate"),
                     r.get("net_price"), r.get("sticker_tuition"),
                     r.get("tuition_in_state"),
                     # Json(None) would write SQL NULL anyway, but an explicit
                     # None keeps "unmeasured" distinct from the empty list a
                     # measured school with no matching families gets.
                     Json(r["programs"]) if r.get("programs") is not None else None,
                     r.get("enrollment"),
                     r["size"], Json(r["majors"]), Json(r["culture"]),
                     Json(r["population"]) if r.get("population") else None,
                     r.get("url"), r.get("net_price_calculator_url"),
                     Json(r.get("details")) if r.get("details") else None,
                     Json(r.get("provenance", {}))),
                )
            # Removals must propagate: schools dropped from the catalog
            # (merged, defunct, or deduplicated) have to leave the table too.
            cur.execute("SELECT id FROM universities")
            existing = {row[0] for row in cur.fetchall()}
            stale = rows_to_delete(existing, {r["id"] for r in rows})
            if stale:
                cur.execute("DELETE FROM universities WHERE id = ANY(%s)", (list(stale),))
                sys.stderr.write(f"pruned {len(stale)} schools no longer in the catalog\n")
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
