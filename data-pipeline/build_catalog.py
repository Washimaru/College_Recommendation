"""Merge the three catalog tiers into the canonical universities.json.

Tier 1  editorial baseline (sources/unimatch_catalog.json) - the only source of
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
    provenance = {
        "avg_gpa": "editorial",
        "culture": "editorial",
        "region": "editorial",
        "setting": "editorial",
        "type": "editorial",
    }

    avg_sat = acceptance_rate = enrollment = sticker = tuition_in_state = None
    net_price = record.get("net_price")
    provenance["net_price"] = "editorial" if net_price is not None else "absent"

    if row is not None:
        avg_sat = parse_number(row.get("SAT_AVG"))
        acceptance_rate = parse_number(row.get("ADM_RATE"))
        enrollment = parse_number(row.get("UGDS"))
        sticker = parse_number(row.get("TUITIONFEE_OUT"))
        tuition_in_state = parse_number(row.get("TUITIONFEE_IN"))
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
    # "In state" is a US concept, and at a private school it is simply the same
    # price as everyone else pays - which the data confirms: all 154 private
    # schools here report identical in- and out-of-state figures.
    if tuition_in_state is not None:
        provenance["tuition_in_state"] = "observed"
    else:
        provenance["tuition_in_state"] = "absent" if is_us else "not_applicable"

    # The school's state, structured. `location` is display-only by rule, so
    # residency can never be decided by parsing it; STABBR is the honest
    # source and is already cached.
    state = _text_or_none(row, "STABBR")
    provenance["state"] = (
        "observed" if state is not None else ("absent" if is_us else "not_applicable")
    )

    programs = awarded_programs(row)
    if programs is not None:
        provenance["programs"] = "observed"
    else:
        provenance["programs"] = "absent" if is_us else "not_applicable"

    outcomes = extract_outcomes(row)
    provenance["outcomes"] = "observed" if outcomes else "absent"

    population = extract_population(row)
    provenance["population"] = (
        "observed" if population else ("absent" if is_us else "not_applicable")
    )

    fallback_size = enrollment if enrollment is not None else record.get("enrollment_editorial")
    return {
        "id": record["id"],
        "unitid": (row or {}).get("UNITID"),
        "name": record["name"],
        "country": record["country"],
        "location": record["location"],
        "state": state,
        "region": record["region"],
        "setting": record["setting"],
        "type": record["type"],
        "avg_gpa": record["avg_gpa"],
        "avg_sat": int(avg_sat) if avg_sat is not None else None,
        "acceptance_rate": acceptance_rate,
        "net_price": net_price,
        "sticker_tuition": sticker,
        "tuition_in_state": tuition_in_state,
        "programs": programs,
        "enrollment": int(enrollment) if enrollment is not None else None,
        "size": size_band(fallback_size),
        "majors": record["majors"],
        "culture": record["culture"],
        "outcomes": outcomes,
        "population": population,
        "url": _text_or_none(row, "INSTURL"),
        "net_price_calculator_url": _text_or_none(row, "NPCURL"),
        "provenance": provenance,
    }


# 2-digit CIP family names, as the Scorecard data dictionary defines them.
# Kept here rather than in the frontend so one list serves the catalog, the
# services and the UI.
CIP_FAMILIES = {
    "PCIP01": "Agriculture",
    "PCIP03": "Natural Resources & Conservation",
    "PCIP04": "Architecture",
    "PCIP05": "Area, Ethnic & Gender Studies",
    "PCIP09": "Communication & Journalism",
    "PCIP10": "Communications Technologies",
    "PCIP11": "Computer & Information Sciences",
    "PCIP12": "Personal & Culinary Services",
    "PCIP13": "Education",
    "PCIP14": "Engineering",
    "PCIP15": "Engineering Technologies",
    "PCIP16": "Foreign Languages & Linguistics",
    "PCIP19": "Family & Consumer Sciences",
    "PCIP22": "Legal Studies",
    "PCIP23": "English Language & Literature",
    "PCIP24": "Liberal Arts & Humanities",
    "PCIP25": "Library Science",
    "PCIP26": "Biological & Biomedical Sciences",
    "PCIP27": "Mathematics & Statistics",
    "PCIP29": "Military Technologies",
    "PCIP30": "Interdisciplinary Studies",
    "PCIP31": "Parks, Recreation & Fitness",
    "PCIP38": "Philosophy & Religious Studies",
    "PCIP39": "Theology & Religious Vocations",
    "PCIP40": "Physical Sciences",
    "PCIP41": "Science Technologies",
    "PCIP42": "Psychology",
    "PCIP43": "Homeland Security & Law Enforcement",
    "PCIP44": "Public Administration & Social Service",
    "PCIP45": "Social Sciences",
    "PCIP46": "Construction Trades",
    "PCIP47": "Mechanic & Repair Technologies",
    "PCIP48": "Precision Production",
    "PCIP49": "Transportation & Materials Moving",
    "PCIP50": "Visual & Performing Arts",
    "PCIP51": "Health Professions",
    "PCIP52": "Business, Management & Marketing",
    "PCIP54": "History",
}


def awarded_programs(row: dict | None) -> list[dict] | None:
    """Degree families a school actually awards, largest share first.

    `None` means nobody measured; `[]` means measured and awarding nothing in
    these families. The distinction is the whole point: only a measured list
    can support "this school does not offer X", and the editorial `majors`
    list cannot, because it names strengths rather than the full catalogue.
    A zero share is omitted rather than listed as 0.0 - "not awarded" is the
    absence of an entry, so a reader cannot mistake it for a tiny programme.
    """
    if row is None:
        return None
    programs = []
    for column, name in CIP_FAMILIES.items():
        share = parse_number(row.get(column))
        if share:
            programs.append({"name": name, "share": round(share, 4)})
    programs.sort(key=lambda p: (-p["share"], p["name"]))
    return programs


# Only these columns are read. The committed cache keeps just these, so it stays
# small enough to review in a diff instead of being a 95 MB blob.
CACHED_COLUMNS = (
    "UNITID", "INSTNM", "CITY", "STABBR",
    "ADM_RATE", "SAT_AVG", "UGDS",
    # Both tuition figures. For 110 of the 113 public schools in this catalog
    # the in-state price is less than half the out-of-state one, so carrying
    # only one of them misstates the cost of a public university by tens of
    # thousands of dollars. They are identical at every private school here,
    # which is why one column looked sufficient for so long.
    "NPT4_PUB", "NPT4_PRIV", "TUITIONFEE_OUT", "TUITIONFEE_IN",
    # Outcomes: what happens after graduation. Federal, and available for
    # 97-99% of matched schools - far better coverage than curated prose.
    "C150_4", "MD_EARN_WNE_P10", "MD_EARN_WNE_P6",
    "GRAD_DEBT_MDN", "PCTPELL", "PCTFLOAN",
    # Student-body composition and the school's own links.
    "UGDS_NRA", "UGDS_WOMEN", "FIRST_GEN", "INSTURL", "NPCURL",
) + tuple(CIP_FAMILIES)

_OUTCOME_COLUMNS = {
    "graduation_rate": "C150_4",
    "median_earnings_10yr": "MD_EARN_WNE_P10",
    "median_earnings_6yr": "MD_EARN_WNE_P6",
    "median_debt": "GRAD_DEBT_MDN",
    "pct_pell": "PCTPELL",
    "pct_federal_loans": "PCTFLOAN",
}

_POPULATION_COLUMNS = {
    "international_share": "UGDS_NRA",
    "women_share": "UGDS_WOMEN",
    "first_gen_share": "FIRST_GEN",
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


def extract_population(row: dict | None) -> dict | None:
    """Student-body shares, or None when the school has none.

    Scorecard covers US institutions only, so this is absent rather than zero
    for every non-US school.
    """
    if row is None:
        return None
    values = {key: parse_number(row.get(col)) for key, col in _POPULATION_COLUMNS.items()}
    if all(v is None for v in values.values()):
        return None
    return values


def _text_or_none(row: dict | None, column: str) -> str | None:
    value = ((row or {}).get(column) or "").strip()
    return value if value and value not in _MISSING else None


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


# Exactly the fields the catalog publishes for a professor. An allowlist, not a
# blocklist: the source could gain a column tomorrow, and a field that reaches a
# public catalog because nobody thought to exclude it is how contact details
# leak. Name, what they are known for, field, whether they are current, how
# widely known, and where to check it.
NOTABLE_FACULTY_FIELDS = (
    "name", "known_for", "fields", "status", "prominence", "source", "source_url",
)


def attach_notable_faculty(record: dict, tier: dict) -> dict:
    """Attach the notable-faculty list for this school, if it was looked up.

    Three states, kept apart deliberately:
      list  - searched, and these are the professors found
      []    - searched, and nobody was found (a real finding for a small school)
      None  - never searched, or a non-US school the source does not cover
    """
    is_us = record["country"] == "USA"
    entry = tier.get(record["id"]) if is_us else None

    if entry is None:
        record["notable_faculty"] = None
        record["provenance"]["notable_faculty"] = "absent" if is_us else "not_applicable"
        return record

    people = []
    for person in entry.get("notable_faculty", []):
        people.append({k: person.get(k) for k in NOTABLE_FACULTY_FIELDS if k in person})
    record["notable_faculty"] = people
    # web_verified, not observed: a Wikipedia category is a published claim
    # about a person, checked by editors rather than measured by a federal
    # survey, and the provenance vocabulary already has a word for that.
    record["provenance"]["notable_faculty"] = "web_verified"
    return record


# The published shape for a researcher. Same allowlist discipline as
# NOTABLE_FACULTY_FIELDS: a source that gains a column tomorrow cannot leak it
# into a public catalog because nobody thought to exclude it.
ACTIVE_FACULTY_FIELDS = (
    "name", "research", "fields", "recent_works", "last_active", "source", "source_url",
)


def attach_active_faculty(record: dict, tier: dict) -> dict:
    """Attach the researchers publishing from this school now.

    `observed` rather than `web_verified`: unlike a Wikipedia category, this is
    counted from publication records — someone either authored papers from this
    address in the last three years or did not.
    """
    is_us = record["country"] == "USA"
    entry = tier.get(record["id"]) if is_us else None

    if entry is None:
        record["active_faculty"] = None
        record["provenance"]["active_faculty"] = "absent" if is_us else "not_applicable"
        return record

    record["active_faculty"] = [
        {k: person.get(k) for k in ACTIVE_FACULTY_FIELDS if k in person}
        for person in entry.get("active_faculty", [])
    ]
    record["provenance"]["active_faculty"] = "observed"
    return record


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
    notable: dict[str, dict] | None = None,
    active: dict[str, dict] | None = None,
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
        enriched = attach_details(enrich(record, row), details or {})
        enriched = attach_notable_faculty(enriched, notable or {})
        catalog.append(attach_active_faculty(enriched, active or {}))
    return catalog, unmatched


def catalog_stats(catalog: list[dict]) -> dict[str, int]:
    """The figures the frontend quotes to a student.

    They live here because the catalog is a build artifact: a rebuild that adds
    or drops a school used to leave "358 universities" standing in five hand-
    edited frontend files, silently wrong on every page.
    """
    return {
        "size": len(catalog),
        "rural": sum(1 for record in catalog if record.get("setting") == "rural"),
        # An empty dict is not a profile; nothing is rendered for it.
        "with_details": sum(1 for record in catalog if record.get("details")),
    }


def render_stats_module(stats: dict[str, int]) -> str:
    """The stats as a TypeScript module the UI imports at build time."""
    return f"""/**
 * Generated by data-pipeline/build_catalog.py - do not edit by hand.
 *
 * The catalog itself (`data-pipeline/out/universities.json`) is a gitignored
 * build artifact, so these counts are committed instead: the hero and the
 * static-demo notice render before any fetch and still have to be honest.
 * Anywhere the catalog is already loaded, count it rather than importing this.
 */

export const CATALOG_SIZE = {stats["size"]};
export const RURAL_COUNT = {stats["rural"]};
export const WITH_DETAILS_COUNT = {stats["with_details"]};
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the canonical university catalog.")
    parser.add_argument("--tier1", default="sources/unimatch_catalog.json")
    parser.add_argument(
        "--scorecard",
        help="Most-Recent-Cohorts-Institution.csv. Only needed to refresh the cache.",
    )
    parser.add_argument("--cache", default="sources/scorecard_cache.json")
    parser.add_argument("--aliases", default="sources/aliases.json")
    parser.add_argument("--details", default="sources/school_details.json")
    parser.add_argument(
        "--active-faculty",
        default="sources/active_faculty.json",
        help="Tier file written by `faculty-pipeline active-faculty`. Absent is fine: "
             "every school's active_faculty then reads null (never searched).",
    )
    parser.add_argument(
        "--notable-faculty",
        default="sources/notable_faculty.json",
        help="Tier file written by `faculty-pipeline notable`. Absent is fine: "
             "every school's notable_faculty then reads null (never searched).",
    )
    parser.add_argument("--out", default="out/universities.json")
    parser.add_argument(
        "--stats-out",
        default=str(
            Path(__file__).resolve().parent.parent / "college-recommender/lib/catalogStats.ts"
        ),
        help="Generated TS module of the counts the UI quotes. Committed, unlike the catalog.",
    )
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

    notable_path = Path(args.notable_faculty)
    notable = (
        json.loads(notable_path.read_text(encoding="utf-8")) if notable_path.exists() else {}
    )
    active_path = Path(args.active_faculty)
    active = (
        json.loads(active_path.read_text(encoding="utf-8")) if active_path.exists() else {}
    )
    if not active:
        sys.stderr.write(
            f"note: no active faculty at {active_path}; active_faculty will be null "
            "for every school (run `faculty-pipeline active-faculty`)\n"
        )

    if not notable:
        sys.stderr.write(
            f"note: no notable faculty at {notable_path}; notable_faculty will be null "
            "for every school (run `faculty-pipeline notable`)\n"
        )

    catalog, unmatched = build(tier1, scorecard, aliases, details, notable, active)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(sorted(catalog, key=lambda r: r["id"]), indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    sys.stderr.write(f"wrote {len(catalog)} universities to {out_path}\n")

    stats = catalog_stats(catalog)
    stats_path = Path(args.stats_out)
    if stats_path.parent.exists():
        stats_path.write_text(render_stats_module(stats), encoding="utf-8")
        sys.stderr.write(f"wrote {stats} to {stats_path}\n")
    else:
        # The pipeline is usable without the frontend checked out beside it.
        sys.stderr.write(f"skipped stats module: {stats_path.parent} does not exist\n")
    if unmatched:
        sys.stderr.write(f"WARNING: {len(unmatched)} US schools unmatched:\n")
        for name in unmatched:
            sys.stderr.write(f"  - {name}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
