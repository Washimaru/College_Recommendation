"""Active faculty — who researches here now, and on what.

The companion to `notable`, answering the question that one cannot: a student
choosing a school wants someone whose class they could take, not a professor
who died in 1984. Sourced from OpenAlex, which knows *when* someone was
affiliated and *what they research*.

Every filter here exists because of something measured on real data
(docs/superpowers/specs/2026-08-14-active-faculty-design.md):

- only authors of works **written from** the institution, because
  `last_known_institutions` put epigenetics researchers on an art school;
- only works from the last few years, because "ever affiliated" surfaced a
  1991 postdoc as MIT faculty;
- only people whose research fields match something the school actually awards
  degrees in, because OpenAlex files 80 JWST astronomy papers under Berklee
  College of Music.

The word "professor" is deliberately not claimed. OpenAlex knows who publishes,
not who holds an appointment, so this list includes some research staff and
misses faculty who do not publish. Titles need the school's own directory,
which is credit-blocked; `source` per entry leaves room for it.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

from ..config import Config
from ..models import School, StageSummary
from ..services.checkpoint import CheckpointStore
from ..services.openalex import (
    OpenAlexApi,
    h_index,
    last_active_year,
    research_fields,
    research_topics,
)

STAGE_NAME = "active-faculty"

DEFAULT_LIMIT = 20

# How many candidate authors to consider before filtering. The pool is ranked
# by publication count, and at a research university the top of that ranking is
# collaboration authors on thousand-author physics papers — who are then
# dropped for not claiming the school. Too small a pool spends itself entirely
# on people who will be rejected: at 60, MIT yielded 6 researchers out of 20.
DEFAULT_POOL = 60

# How far back still counts as "here now". Three years covers a normal
# publication gap without reaching back to people who have since moved on.
RECENT_YEARS = 3

# OpenAlex research field -> the CIP families a school awarding degrees in it
# would have. Used only to reject the implausible: an author whose fields match
# nothing the school teaches is dropped. Deliberately generous — the cost of a
# missing entry is a shorter list, the cost of a false one is a music college
# with astronomers on its page.
FIELD_TO_FAMILIES: dict[str, tuple[str, ...]] = {
    "Physics and Astronomy": ("Physical Sciences", "Engineering"),
    "Chemistry": ("Physical Sciences", "Engineering"),
    "Earth and Planetary Sciences": ("Physical Sciences", "Natural Resources & Conservation"),
    "Environmental Science": ("Natural Resources & Conservation", "Physical Sciences"),
    "Mathematics": ("Mathematics & Statistics", "Computer & Information Sciences"),
    "Computer Science": ("Computer & Information Sciences", "Engineering"),
    "Engineering": ("Engineering", "Engineering Technologies", "Architecture"),
    "Materials Science": ("Engineering", "Physical Sciences"),
    "Chemical Engineering": ("Engineering",),
    "Energy": ("Engineering", "Physical Sciences"),
    "Biochemistry, Genetics and Molecular Biology": ("Biological & Biomedical Sciences",),
    "Agricultural and Biological Sciences": ("Agriculture", "Biological & Biomedical Sciences",
                                             "Natural Resources & Conservation"),
    "Immunology and Microbiology": ("Biological & Biomedical Sciences", "Health Professions"),
    "Neuroscience": ("Biological & Biomedical Sciences", "Psychology", "Health Professions"),
    "Medicine": ("Health Professions", "Biological & Biomedical Sciences"),
    "Nursing": ("Health Professions",),
    "Dentistry": ("Health Professions",),
    "Veterinary": ("Health Professions", "Agriculture"),
    "Health Professions": ("Health Professions",),
    "Pharmacology, Toxicology and Pharmaceutics": ("Health Professions",
                                                   "Biological & Biomedical Sciences"),
    "Psychology": ("Psychology", "Social Sciences"),
    "Social Sciences": ("Social Sciences", "Public Administration & Social Service",
                        "Area, Ethnic & Gender Studies", "Education", "Legal Studies"),
    "Economics, Econometrics and Finance": ("Social Sciences",
                                            "Business, Management & Marketing"),
    "Business, Management and Accounting": ("Business, Management & Marketing",),
    "Decision Sciences": ("Business, Management & Marketing", "Mathematics & Statistics"),
    "Arts and Humanities": ("Visual & Performing Arts", "English Language & Literature",
                            "History", "Philosophy & Religious Studies",
                            "Foreign Languages & Linguistics", "Liberal Arts & Humanities",
                            "Communication & Journalism", "Architecture",
                            "Theology & Religious Vocations"),
}


def affiliated_recently(author: dict, institution_id: str, since_year: int) -> bool:
    """Does this author's own record claim the school in recent years?

    "Wrote a paper from here" is not "works here". A CMS/ATLAS paper carries
    thousands of authors and credits every participating institution, which
    made MIT's top three M. Tytgat (Ghent), R. Klanner (DESY) and Y. Yang.
    Their own affiliation records name Lyon, Riverside, Rome, Caltech — not
    MIT. Measured: of 50 MIT candidates, 6 claim MIT recently.

    An empty affiliation list means unmeasured, not absent, and is kept — the
    same rule the catalog applies to every other missing fact.
    """
    affiliations = author.get("affiliations") or []
    if not affiliations:
        return True
    for entry in affiliations:
        ident = ((entry.get("institution") or {}).get("id") or "").rsplit("/", 1)[-1]
        if ident == institution_id and any(y >= since_year for y in entry.get("years") or []):
            return True
    return False


def match_name(name: str) -> str:
    """A name reduced to what the two lists can agree on.

    Wikipedia writes "Mary McCarthy (American writer)" and keeps the accent in
    "Rosemary Lévy Zumwalt"; OpenAlex does neither. Exact matching missed both.

    This recovers a handful of people, not hundreds — only 10 names are shared
    between the 2,366 award-holders and the 3,165 active researchers, because
    Wikipedia's faculty categories and OpenAlex's recent publishers are largely
    different populations. The h-index carries the ranking; an award is a bonus
    on top of it.
    """
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    folded = re.sub(r"\s*\(.*?\)", "", folded)
    return " ".join(re.sub(r"[^A-Za-z ]", " ", folded).lower().split())


class ActiveFacultyError(RuntimeError):
    """Fatal stage error — not a per-school failure."""


def plausible_here(fields: list[str], families: set[str]) -> bool:
    """Could someone whose main research area is `fields[0]` work at this school?

    Judged on the **primary** field only. Matching on any field is too weak:
    Berklee College of Music awards no physical-science degrees, but four JWST
    astronomers passed anyway because one of their topics touched Computer
    Science, which Berklee does award. Their primary field is Physics and
    Astronomy, and that is what they actually do.

    The cost is real and worth stating: a music college's political-economy
    lecturer is dropped too, because PCIP records *degrees awarded* and no
    music college awards social-science degrees. So this list covers research
    faculty working in the school's own degree areas — not everyone who
    teaches there. Showing four astronomers to someone considering Berklee is
    the worse error.

    True by default when the school's degree data is missing: an absent
    catalog fact is not evidence against a person.
    """
    if not families:
        return True
    if not fields:
        return False
    return bool(set(FIELD_TO_FAMILIES.get(fields[0], ())) & families)


def run(
    config: Config,
    checkpoint: CheckpointStore,
    logger: logging.Logger,
    api: OpenAlexApi,
    *,
    programs_by_school: dict[str, set[str]] | None = None,
    honours_by_school: dict[str, dict[str, list[str]]] | None = None,
    limit: int | None = None,
    school_id: str | None = None,
    per_school: int = DEFAULT_LIMIT,
    pool_size: int = DEFAULT_POOL,
    dry_run: bool = False,
) -> StageSummary:
    """Resumable per school. `programs_by_school` supplies the degree families
    the plausibility check tests against; without it nothing is rejected."""
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

    out_path = Path(config.data_dir) / "active_faculty.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    since = datetime.now(UTC).year - RECENT_YEARS

    processed = failed = 0
    unresolved: list[str] = []
    empty: list[str] = []
    rejected_total = {"elsewhere": 0, "field": 0}

    with out_path.open("a", encoding="utf-8") as out:
        for school in pending:
            try:
                people, institution, rejected = _active_for(
                    api, school, since, per_school, pool_size,
                    (programs_by_school or {}).get(school.school_id, set()),
                    (honours_by_school or {}).get(school.school_id, {}),
                    logger,
                )
            except Exception as exc:  # noqa: BLE001 - one school is not the run
                failed += 1
                checkpoint.mark_failed(school.school_id, str(exc))
                logger.warning(
                    "active-faculty failed: %s", exc,
                    extra={"stage": STAGE_NAME, "school_id": school.school_id},
                )
                continue

            for reason, n in rejected.items():
                rejected_total[reason] += n
            out.write(json.dumps({
                "school_id": school.school_id,
                "school_name": school.name,
                "active_faculty": people,
                "institution": institution,
                "retrieved_at": datetime.now(UTC).date().isoformat(),
            }, ensure_ascii=False))
            out.write("\n")
            out.flush()
            checkpoint.mark_done(school.school_id, meta={"found": len(people)})
            processed += 1
            if institution is None:
                unresolved.append(school.school_id)
            elif not people:
                empty.append(school.school_id)
            logger.info(
                "active-faculty: %s -> %d researcher(s)%s",
                school.school_id, len(people),
                _rejection_phrase(rejected),
                extra={"stage": STAGE_NAME, "school_id": school.school_id},
            )

    notes = [f"{processed} school(s) resolved, {failed} failed, {already} already done"]
    if rejected_total["elsewhere"]:
        notes.append(
            f"{rejected_total['elsewhere']} author(s) dropped: published from the school but "
            "their own affiliation record names somewhere else (thousand-author papers credit "
            "every participating institution)"
        )
    if rejected_total["field"]:
        notes.append(
            f"{rejected_total['field']} author(s) dropped: their research fields match nothing "
            "the school awards degrees in (OpenAlex mis-attributes whole bodies of work)"
        )
    if unresolved:
        notes.append(
            f"{len(unresolved)} school(s) had no confirmable OpenAlex institution: "
            + ", ".join(sorted(unresolved)[:8]) + (" …" if len(unresolved) > 8 else "")
        )
    if empty:
        notes.append(
            f"{len(empty)} school(s) resolved but published nothing recent: "
            + ", ".join(sorted(empty)[:8]) + (" …" if len(empty) > 8 else "")
        )

    return StageSummary(
        stage=STAGE_NAME, processed=processed, skipped=already, failed=failed,
        started_at=started_at, finished_at=datetime.now(UTC), notes=notes,
    )


def _active_for(
    api: OpenAlexApi,
    school: School,
    since: int,
    per_school: int,
    pool_size: int,
    families: set[str],
    honours: dict[str, list[str]],
    logger: logging.Logger,
) -> tuple[list[dict], str | None, int]:
    institution = api.institution_for(school.name, school.homepage)
    if institution is None:
        return [], None, {"elsewhere": 0, "field": 0}
    institution_id = institution["id"].rsplit("/", 1)[-1]

    counts = api.recent_author_counts(institution_id, since, limit=max(pool_size, per_school))
    if not counts:
        return [], institution_id, {"elsewhere": 0, "field": 0}

    authors = api.authors([author_id for author_id, _, _ in counts])

    people: list[dict] = []
    # Counted apart, because they mean different things and the note names
    # them: `elsewhere` is someone who never claimed this school, `field` is
    # someone whose research it does not teach.
    rejected = {"elsewhere": 0, "field": 0}
    for author_id, display_name, works in counts:
        author = authors.get(author_id)
        if author is None:
            continue
        if not affiliated_recently(author, institution_id, since):
            rejected["elsewhere"] += 1
            continue
        fields = research_fields(author)
        if not plausible_here(fields, families):
            rejected["field"] += 1
            continue
        name = author.get("display_name") or display_name
        people.append({
            "name": name,
            "research": research_topics(author),
            "fields": fields[:3],
            "recent_works": works,
            "last_active": last_active_year(author),
            "h_index": h_index(author),
            # Awards come from the notable list, which carries Wikidata's P166
            # for anyone with a Wikipedia article. Matched on name within one
            # school, which is narrow enough to be safe.
            "awards": honours.get(match_name(name), []),
            "source": "openalex",
            "source_url": author["id"],
        })

    # Priority, in the order a student would care about it: someone recognised
    # for their research, then someone whose work is widely built on, then
    # someone simply publishing a lot from here.
    people.sort(
        key=lambda p: (
            bool(p["awards"]),
            p["h_index"] or 0,
            p["recent_works"] or 0,
        ),
        reverse=True,
    )
    return people[:per_school], institution_id, rejected


def write_tier_file(data_dir: str | Path, tier_path: str | Path) -> int:
    """Fold the per-school JSONL into the committed tier file, last write wins."""
    source = Path(data_dir) / "active_faculty.jsonl"
    if not source.exists():
        raise ActiveFacultyError(f"no active faculty at {source}. Run `active-faculty` first.")
    by_school: dict[str, dict] = {}
    for line in source.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            by_school[record["school_id"]] = record
    out = Path(tier_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(dict(sorted(by_school.items())), indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return len(by_school)


def _rejection_phrase(rejected: dict[str, int]) -> str:
    parts = []
    if rejected["elsewhere"]:
        parts.append(f"{rejected['elsewhere']} affiliated elsewhere")
    if rejected["field"]:
        parts.append(f"{rejected['field']} outside its fields")
    return f" ({', '.join(parts)})" if parts else ""


def _load_schools(data_dir: str | Path) -> list[School]:
    path = Path(data_dir) / "schools.jsonl"
    if not path.exists():
        raise ActiveFacultyError(
            f"schools not found at {path}. Run `python -m faculty_pipeline load` first."
        )
    return [
        School.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
