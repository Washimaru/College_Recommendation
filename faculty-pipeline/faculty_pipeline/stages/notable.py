"""Notable faculty — named professors per school, from structured sources.

Distinct from stages 1-5, which chase a school's *complete* directory and
produce contact details. This answers a different question — "who teaches
here that a student might want to read about" — from Wikipedia category
membership plus Wikidata, and so:

- **cannot invent a person.** No LLM is involved at any point. A professor is
  either in the category and the item store, or is not in the output.
- **needs no API credits**, which matters because the extract stage's do.
- **publishes nothing private.** Name, what they are known for, field, whether
  they are current or historical, and a link. No email, no phone. That line is
  the existing one: the faculty CSVs stay gitignored because they aggregate
  contact details, not because a named professor's employer is a secret.

Per school: resolve the faculty category, list its members, drop the pages that
are not people, rank what remains by how many language Wikipedias carry an
article, and keep the top `limit`. A school with three findable professors gets
three - the list is never padded.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from ..config import Config
from ..models import School, StageSummary
from ..services.checkpoint import CheckpointStore
from ..services.wikimedia import (
    MediaWikiApi,
    claim_ids,
    english_description,
    has_died,
    is_human,
    sitelink_count,
)

STAGE_NAME = "notable"

# Pages that sit in a faculty category without being a person.
_NON_PERSON_PREFIXES = ("List of", "Category:", "Template:", "Portal:", "Draft:", "File:")

# How many to keep per school. The brief asked for 10-20; 20 is the ceiling
# and there is no floor, because inventing the difference is the one thing
# this stage must never do.
DEFAULT_LIMIT = 20

# Occupations that say nothing useful about what someone teaches. Dropped from
# the displayed field list, never from the person.
_UNINFORMATIVE_OCCUPATIONS = {"researcher", "university teacher", "academic", "scientist"}


class NotableError(RuntimeError):
    """Fatal stage error (e.g. no schools file) — not a per-school failure."""


def category_for(school: School) -> str:
    """The English Wikipedia faculty category for a school.

    The plain catalog name works: measured across a 12-school sample spanning
    a tiny liberal-arts college, an art school, two flagship publics and an
    Ivy, it resolved 12 out of 12. A school that misses is reported, not
    guessed at.
    """
    return f"Category:{school.name} faculty"


def run(
    config: Config,
    checkpoint: CheckpointStore,
    logger: logging.Logger,
    api: MediaWikiApi,
    *,
    limit: int | None = None,
    school_id: str | None = None,
    per_school: int = DEFAULT_LIMIT,
    dry_run: bool = False,
) -> StageSummary:
    """Resumable per school. `limit` caps how many schools this run touches."""
    started_at = datetime.now(UTC)
    schools = [s for s in _load_schools(config.data_dir) if s.country == "US"]
    targets = [s for s in schools if school_id is None or s.school_id == school_id]
    pending = [s for s in targets if not checkpoint.is_done(s.school_id)]
    already = len(targets) - len(pending)
    if limit is not None:
        pending = pending[:limit]

    if dry_run:
        return StageSummary(
            stage=STAGE_NAME, processed=0, skipped=already + len(pending), failed=0,
            started_at=started_at, finished_at=datetime.now(UTC),
            notes=[f"[dry-run] would look up {len(pending)} school(s); no requests made"],
        )

    out_path = Path(config.data_dir) / "notable_faculty.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    processed = failed = 0
    empty: list[str] = []
    thin: list[str] = []

    with out_path.open("a", encoding="utf-8") as out:
        for school in pending:
            try:
                category, people = _notable_for(api, school, per_school, logger)
            except Exception as exc:  # noqa: BLE001 - one school is not the run
                failed += 1
                checkpoint.mark_failed(school.school_id, str(exc))
                logger.warning(
                    "notable failed: %s", exc,
                    extra={"stage": STAGE_NAME, "school_id": school.school_id},
                )
                continue

            out.write(json.dumps({
                "school_id": school.school_id,
                "school_name": school.name,
                "notable_faculty": people,
                # Recorded so a thin result can be checked against the category
                # it actually came from rather than the one someone assumes.
                "category": category,
                "retrieved_at": datetime.now(UTC).date().isoformat(),
            }, ensure_ascii=False))
            out.write("\n")
            out.flush()
            checkpoint.mark_done(school.school_id, meta={"found": len(people)})
            processed += 1
            if not people:
                empty.append(school.school_id)
            elif len(people) < 10:
                thin.append(f"{school.school_id} ({len(people)})")
            logger.info(
                "notable: %s -> %d professor(s)", school.school_id, len(people),
                extra={"stage": STAGE_NAME, "school_id": school.school_id},
            )

    notes = [f"{processed} school(s) resolved, {failed} failed, {already} already done"]
    if empty:
        notes.append(
            f"{len(empty)} school(s) yielded nobody at all: {', '.join(sorted(empty)[:8])}"
            + (" …" if len(empty) > 8 else "")
        )
    if thin:
        notes.append(
            f"{len(thin)} school(s) yielded fewer than 10, which is reported rather "
            f"than padded: {', '.join(sorted(thin)[:8])}" + (" …" if len(thin) > 8 else "")
        )

    return StageSummary(
        stage=STAGE_NAME, processed=processed, skipped=already, failed=failed,
        started_at=started_at, finished_at=datetime.now(UTC), notes=notes,
    )


def resolve_category(
    api: MediaWikiApi, school: School, logger: logging.Logger
) -> tuple[str, list[str]]:
    """The faculty category that actually holds this school's professors.

    Three steps, cheapest first, because 248 of 268 schools resolve on the
    first one and should not pay for the others:

    1. the catalog name — `Category:<name> faculty`;
    2. the name Wikipedia redirects to, since "Georgia Institute of
       Technology" is filed under "Georgia Tech" and "University of Maryland"
       under "University of Maryland, College Park";
    3. the article a search finds, for names that are neither a title nor a
       redirect - "Binghamton University (SUNY)" carries the catalog's own
       disambiguation, not Wikipedia's, and search resolves it to
       "Binghamton University" and its 144 professors;
    4. a search of the category namespace, for the genuinely irregular:
       "Hamilton College (New York) faculty", and Cal State Fullerton's, which
       carries a stray comma before the word "faculty".

    Returns the category tried last and whatever it held. An empty list after
    all three is a real answer - two schools in this catalog have no faculty
    category on Wikipedia at all.
    """
    category = category_for(school)
    titles = _people_pages(api, category)
    if titles:
        return category, titles

    canonical = api.canonical_title(school.name)
    if canonical and canonical != school.name:
        redirected = f"Category:{canonical} faculty"
        titles = _people_pages(api, redirected)
        if titles:
            logger.info(
                "notable: %s resolved via redirect to %r", school.school_id, canonical,
                extra={"stage": STAGE_NAME, "school_id": school.school_id},
            )
            return redirected, titles

    found = api.search_article(school.name)
    if found and found not in (school.name, canonical):
        by_search = f"Category:{found} faculty"
        titles = _people_pages(api, by_search)
        if titles:
            logger.info(
                "notable: %s resolved by article search to %r", school.school_id, found,
                extra={"stage": STAGE_NAME, "school_id": school.school_id},
            )
            return by_search, titles

    searched = api.search_faculty_category(school.name)
    if searched:
        titles = _people_pages(api, searched)
        if titles:
            logger.info(
                "notable: %s resolved by category search to %r", school.school_id, searched,
                extra={"stage": STAGE_NAME, "school_id": school.school_id},
            )
            return searched, titles

    return category, []


def _people_pages(api: MediaWikiApi, category: str) -> list[str]:
    return [
        t for t in api.category_members(category)
        if not t.startswith(_NON_PERSON_PREFIXES)
    ]


def _notable_for(
    api: MediaWikiApi, school: School, per_school: int, logger: logging.Logger
) -> tuple[str, list[dict]]:
    category, titles = resolve_category(api, school, logger)
    if not titles:
        return category, []

    qids = api.wikidata_ids(titles)
    if not qids:
        return category, []
    entities = api.entities(list(qids.values()))

    people: list[dict] = []
    occupation_ids: set[str] = set()
    for title, qid in qids.items():
        entity = entities.get(qid)
        # A page in the category that is not a human is a list, a building or
        # a research centre — dropped, not guessed at.
        if not entity or not is_human(entity):
            continue
        occupations = claim_ids(entity, "P106")
        occupation_ids.update(occupations)
        people.append({
            "name": title,
            "known_for": english_description(entity),
            "_occupation_ids": occupations,
            "status": "historical" if has_died(entity) else "current",
            "prominence": sitelink_count(entity),
            "source": "wikipedia",
            "source_url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
        })

    labels = api.labels(sorted(occupation_ids)) if occupation_ids else {}
    for person in people:
        fields = [labels[q] for q in person.pop("_occupation_ids") if q in labels]
        person["fields"] = [
            f for f in fields if f.lower() not in _UNINFORMATIVE_OCCUPATIONS
        ][:4]

    # Most widely known first, then alphabetically so the order is stable
    # between runs rather than dependent on category paging.
    people.sort(key=lambda p: (-p["prominence"], p["name"]))
    return category, people[:per_school]


def write_tier_file(data_dir: str | Path, tier_path: str | Path) -> int:
    """Fold the per-school JSONL into the committed tier file the catalog reads.

    Committed, unlike `master.csv`, because it holds no contact details and the
    catalog build has to stay reproducible offline. Last record per school
    wins, so a re-run of one school corrects it.
    """
    source = Path(data_dir) / "notable_faculty.jsonl"
    if not source.exists():
        raise NotableError(f"no notable faculty at {source}. Run `notable` first.")
    by_school: dict[str, dict] = {}
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            by_school[record["school_id"]] = record
    # Every school that was looked at, including the ones that yielded nobody:
    # "measured, found none" is a different fact from "never measured", and the
    # catalog draws that distinction ([] vs null) exactly as it does for
    # `programs`. Dropping the empties here would collapse the two.
    payload = {school_id: record for school_id, record in sorted(by_school.items())}
    out = Path(tier_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(payload)


def _load_schools(data_dir: str | Path) -> list[School]:
    path = Path(data_dir) / "schools.jsonl"
    if not path.exists():
        raise NotableError(
            f"schools not found at {path}. Run `python -m faculty_pipeline load` first."
        )
    return [
        School.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
