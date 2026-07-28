"""Merge the three catalog tiers into the canonical universities.json.

Tier 1  editorial baseline (sources/unimatch_364.json) - the only source of
        avg_gpa and the culture vector.
Tier 2  College Scorecard bulk CSV - observed US federal statistics.
Tier 3  manual overrides - hand-curated, each entry citing a source.

Governing rule: a wrong number is worse than a null. Nothing is ever derived
from another field and presented as independent data.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

# Scorecard writes missing values as the literal string NA. Treating only empty
# cells as missing reads 100% coverage where the truth is 16%.
_MISSING = {"", "NA", "NULL", "PrivacySuppressed"}

# Size bands. Proposed, not inherited - no prior code derived a band from a
# headcount. Worth revisiting against the real distribution.
_SMALL_MAX = 5_000
_MEDIUM_MAX = 15_000


def normalize_name(name: str) -> str:
    """Fold the naming differences between common usage and Scorecard.

    Scorecard uses hyphens where common usage uses commas
    (`University of California-Berkeley`), appends campus qualifiers
    (`-Main Campus`), and the tier-1 dataset uses an en-dash in
    `University of Wisconsin-Madison`.
    """
    folded = name.lower().strip().replace("–", "-").replace("—", "-")
    folded = re.sub(r",\s*", "-", folded)
    folded = re.sub(r"-main campus$", "", folded)
    folded = re.sub(r"\bthe\b|\bat\b", "", folded)
    return re.sub(r"[^a-z0-9]+", "", folded)


def parse_number(value: str | None) -> float | None:
    """Scorecard cell -> float, or None when missing/unparseable."""
    if value is None or str(value).strip() in _MISSING:
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def coalesce_net_price(row: dict) -> float | None:
    """NPT4_PUB and NPT4_PRIV are public/private variants of one measure; a
    school has exactly one. Non-positive values are bad data, not a discount."""
    for column in ("NPT4_PUB", "NPT4_PRIV"):
        value = parse_number(row.get(column))
        if value is not None and value > 0:
            return value
    return None


def size_band(enrollment: float | None) -> str:
    if enrollment is None:
        return "medium"
    if enrollment < _SMALL_MAX:
        return "small"
    if enrollment < _MEDIUM_MAX:
        return "medium"
    return "large"


def enrich(record: dict, row: dict | None) -> dict:
    """Merge one tier-2 Scorecard row onto a tier-1 record.

    Tier 2 fills observed values and overrides editorial estimates for the
    fields it measures. avg_gpa and culture always stay tier 1 - no public
    source publishes them.
    """
    is_us = record["country"] == "USA"
    provenance = {"avg_gpa": "editorial", "culture": "editorial"}

    avg_sat = acceptance_rate = enrollment = sticker = None
    net_price = record.get("net_price")
    provenance["net_price"] = "editorial" if net_price is not None else "absent"

    if row is not None:
        avg_sat = parse_number(row.get("SAT_AVG"))
        acceptance_rate = parse_number(row.get("ADM_RATE"))
        enrollment = parse_number(row.get("UGDS"))
        sticker = parse_number(row.get("TUITIONFEE_OUT"))
        observed_net = coalesce_net_price(row)
        if observed_net is not None:
            net_price = observed_net
            provenance["net_price"] = "observed"

    # The SAT is not used outside the US. `not_applicable` is deliberately
    # distinct from `absent`: it must not read as a gap someone should fill.
    provenance["avg_sat"] = (
        "observed" if avg_sat is not None else ("absent" if is_us else "not_applicable")
    )
    provenance["acceptance_rate"] = "observed" if acceptance_rate is not None else "absent"
    provenance["enrollment"] = "observed" if enrollment is not None else "absent"
    provenance["sticker_tuition"] = "observed" if sticker is not None else "absent"

    outcomes = extract_outcomes(row)
    provenance["outcomes"] = "observed" if outcomes else "absent"

    fallback_size = enrollment if enrollment is not None else record.get("enrollment_editorial")
    return {
        "id": record["id"],
        "unitid": (row or {}).get("UNITID"),
        "name": record["name"],
        "country": record["country"],
        "location": record["location"],
        "avg_gpa": record["avg_gpa"],
        "avg_sat": int(avg_sat) if avg_sat is not None else None,
        "acceptance_rate": acceptance_rate,
        "net_price": net_price,
        "sticker_tuition": sticker,
        "enrollment": int(enrollment) if enrollment is not None else None,
        "size": size_band(fallback_size),
        "majors": record["majors"],
        "culture": record["culture"],
        "outcomes": outcomes,
        "provenance": provenance,
    }


# Only these columns are read. The committed cache keeps just these, so it stays
# small enough to review in a diff instead of being a 95 MB blob.
CACHED_COLUMNS = (
    "UNITID", "INSTNM", "CITY", "STABBR",
    "ADM_RATE", "SAT_AVG", "UGDS",
    "NPT4_PUB", "NPT4_PRIV", "TUITIONFEE_OUT",
    # Outcomes: what happens after graduation. Federal, and available for
    # 97-99% of matched schools - far better coverage than curated prose.
    "C150_4", "MD_EARN_WNE_P10", "MD_EARN_WNE_P6",
    "GRAD_DEBT_MDN", "PCTPELL", "PCTFLOAN",
)

_OUTCOME_COLUMNS = {
    "graduation_rate": "C150_4",
    "median_earnings_10yr": "MD_EARN_WNE_P10",
    "median_earnings_6yr": "MD_EARN_WNE_P6",
    "median_debt": "GRAD_DEBT_MDN",
    "pct_pell": "PCTPELL",
    "pct_federal_loans": "PCTFLOAN",
}


def extract_outcomes(row: dict | None) -> dict | None:
    """Post-graduation figures from the Scorecard row, or None when the school
    has none. Individual fields stay null rather than being filled in."""
    if row is None:
        return None
    values = {key: parse_number(row.get(col)) for key, col in _OUTCOME_COLUMNS.items()}
    if all(v is None for v in values.values()):
        return None
    return values


def resolve_key(record: dict, aliases: dict[str, str]) -> str:
    return normalize_name(aliases.get(record["name"], record["name"]))


def filter_cache(
    tier1: list[dict], index: dict[str, dict], aliases: dict[str, str]
) -> dict[str, dict]:
    """Reduce the full Scorecard index to the rows and columns this catalog
    actually uses, so the cache can be committed for offline, auditable builds."""
    cache: dict[str, dict] = {}
    for record in tier1:
        if record["country"] != "USA":
            continue
        key = resolve_key(record, aliases)
        row = index.get(key)
        if row is not None:
            cache[key] = {column: row.get(column) for column in CACHED_COLUMNS}
    return cache


# Curated details exist for a minority of schools. `_source` records which tier
# a profile came from so the UI can label it, and a school with none carries
# `details: None` rather than generated filler.
_DETAIL_PROVENANCE = {
    "curated": "observed",
    "web_verified": "web_verified",
    "estimated": "editorial",
}


def attach_details(record: dict, details_by_id: dict[str, dict]) -> dict:
    """Attach a per-school profile (scholarships, research, outcomes, grad and
    professional schools) when one exists."""
    profile = details_by_id.get(record["id"])
    if not profile:
        record["details"] = None
        record["provenance"]["details"] = "absent"
        return record

    source = profile.get("_source", "curated")
    record["details"] = {k: v for k, v in profile.items() if k != "_source"}
    record["provenance"]["details"] = _DETAIL_PROVENANCE.get(source, "editorial")
    return record


def index_scorecard(csv_path: Path) -> dict[str, dict]:
    """Index the Scorecard CSV by normalized institution name."""
    index: dict[str, dict] = {}
    with csv_path.open(encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            index.setdefault(normalize_name(row.get("INSTNM") or ""), row)
    return index


def build(
    tier1: list[dict],
    scorecard: dict[str, dict],
    aliases: dict[str, str] | None = None,
    details: dict[str, dict] | None = None,
) -> tuple[list[dict], list[str]]:
    """Return (catalog, unmatched_us_names). Unmatched names are surfaced so
    the coverage gap is visible rather than silent."""
    aliases = aliases or {}
    catalog, unmatched = [], []
    for record in tier1:
        row = None
        if record["country"] == "USA":
            row = scorecard.get(resolve_key(record, aliases))
            if row is None:
                unmatched.append(record["name"])
        catalog.append(attach_details(enrich(record, row), details or {}))
    return catalog, unmatched


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the canonical university catalog.")
    parser.add_argument("--tier1", default="sources/unimatch_364.json")
    parser.add_argument(
        "--scorecard",
        help="Most-Recent-Cohorts-Institution.csv. Only needed to refresh the cache.",
    )
    parser.add_argument("--cache", default="sources/scorecard_cache.json")
    parser.add_argument("--aliases", default="sources/aliases.json")
    parser.add_argument("--details", default="sources/school_details.json")
    parser.add_argument("--out", default="out/universities.json")
    args = parser.parse_args(argv)

    tier1 = json.loads(Path(args.tier1).read_text(encoding="utf-8"))
    aliases_path = Path(args.aliases)
    aliases = json.loads(aliases_path.read_text(encoding="utf-8")) if aliases_path.exists() else {}
    # Keys beginning with "_" are documentation, not aliases.
    aliases = {k: v for k, v in aliases.items() if not k.startswith("_")}

    cache_path = Path(args.cache)
    if args.scorecard:
        scorecard = filter_cache(tier1, index_scorecard(Path(args.scorecard)), aliases)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(scorecard, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        sys.stderr.write(f"refreshed cache: {len(scorecard)} rows -> {cache_path}\n")
    elif cache_path.exists():
        scorecard = json.loads(cache_path.read_text(encoding="utf-8"))
    else:
        sys.stderr.write(f"no cache at {cache_path}; pass --scorecard to build one\n")
        return 2

    details_path = Path(args.details)
    details = json.loads(details_path.read_text(encoding="utf-8")) if details_path.exists() else {}

    catalog, unmatched = build(tier1, scorecard, aliases, details)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(sorted(catalog, key=lambda r: r["id"]), indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    sys.stderr.write(f"wrote {len(catalog)} universities to {out_path}\n")
    if unmatched:
        sys.stderr.write(f"WARNING: {len(unmatched)} US schools unmatched:\n")
        for name in unmatched:
            sys.stderr.write(f"  - {name}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
