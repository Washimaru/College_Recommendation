"""Stage 4 — Extract & Normalize (§6 Stage 4).

For each `RawProfile` not already `done` in `checkpoints/extract.json`:

1. **Non-200 short-circuit.** A profile URL that didn't resolve (§4.3's
   `http_status`, most commonly a 404) is not a person and is never sent to
   the LLM at all — it's recorded `done` with no row, per the M5 instruction
   that a 404 page must not become a row.
2. **Deterministic pass.** Strip the cached HTML to readable text; pull
   `mailto:` emails, `tel:` phones, `<meta>` tags, and JSON-LD `Person`
   blocks; de-obfuscate common email patterns ("name [at] domain.edu",
   "name (at) domain (dot) edu", "name AT domain DOT edu") and plain emails
   written directly as text. These become both the `hints` passed to the LLM
   and the grounding set used to verify its answer.
3. **LLM pass** (skippable via `no_llm=True`, for debugging).
   `services.llm.extract_professor` returns an untrusted
   `ProfessorExtraction` — a structured guess, including an explicit
   `is_profile` flag so a directory index, 404, news article, or department
   landing page that slipped through crawling can say "this is not an
   individual's profile" and have that respected: no row, not an invented
   name from a page title.
4. **Validate — this stage is the trust boundary.** `professor_name` is
   required (no name, no row). An `email`/`phone` the LLM returned is kept
   only if it is actually grounded in the page — it appears verbatim in the
   cleaned text or matches a deterministic hint pulled from the raw HTML.
   Anything not grounded is dropped rather than trusted, because "the model
   said so" is not evidence a human typed it on this page. The
   `professor_name` also gets a defense-in-depth boilerplate strip (the
   `<title>`-derived hint's " | School Name" trap, §6 Stage 4 / crawl.py's
   `_parse_hint`) even though the prompt already tells the model not to
   include it.

Appends validated rows to `data/profiles_clean.jsonl`; checkpoints per
profile URL; LLM responses are cached by prompt hash under `cache/llm/`
(services/llm.py), so re-running extract after a `--force` crawl is nearly
free — a cache hit never calls the API.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.parse import unquote

from selectolax.parser import HTMLParser

from ..config import Config
from ..models import Professor, RawProfile, School, StageSummary
from ..services.checkpoint import CheckpointStore
from ..services.llm import ExtractionFailed, ProfessorExtraction
from ..utils import classify_role

STAGE_NAME = "extract"

# A deterministic-only (`--no-llm`) row carries no LLM judgment at all, so it
# gets a fixed, middling confidence rather than a computed one — low enough
# that Stage 5's confidence floor (§13, default 0.5) doesn't wave it through
# as if an LLM had verified it, but not 0 either, since the fields it does
# carry (name/email/phone from JSON-LD, meta tags, mailto:/tel:) are the
# highest-reliability deterministic sources in the pipeline.
_NO_LLM_CONFIDENCE = 0.5

_NOISE_TAGS = ("script", "style", "noscript", "svg", "nav", "footer", "header")

_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE_RE = re.compile(
    r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}(?:\s*(?:x|ext\.?)\s*\d{1,6})?",
    re.IGNORECASE,
)

# De-obfuscation (§6 Stage 4 / M5): normalize the common markers to literal
# '@'/'.' and then run the plain email regex over the result. Bare AT/DOT
# must be uppercase and adjacent to identifier characters, or ordinary prose
# ("look at the DOT on the map") would be swept in as an email.
_BRACKET_AT_RE = re.compile(r"\s*[\[(]\s*at\s*[\])]\s*", re.IGNORECASE)
_BRACKET_DOT_RE = re.compile(r"\s*[\[(]\s*dot\s*[\])]\s*", re.IGNORECASE)
_BARE_AT_RE = re.compile(r"(?<=[\w.])\s+AT\s+(?=[\w.])")
_BARE_DOT_RE = re.compile(r"(?<=[\w])\s+DOT\s+(?=[\w])")

# The `<title>`/`<h1>`-derived `parse_hint` (crawl.py) trap this M5 build
# specifically calls out: "Thalita Abrahao | Agnes Scott College". Any of
# these separators followed by (a close match to) the school's own name is
# stripped before the remainder is trusted as a name.
_BOILERPLATE_SEPARATORS = (" | ", " - ", " – ", " — ", " :: ", ": ")


class ExtractError(RuntimeError):
    """Fatal Stage 4 error (e.g. missing `data/profiles_raw.jsonl`) — not a
    per-item failure."""


class ProfessorExtractor(Protocol):
    """The subset of `services.llm.LLM` this stage needs. A Protocol so
    tests can inject a fake client without a real network stack."""

    def extract_professor(
        self,
        text: str,
        url: str,
        school: School,
        hints: dict[str, str | None] | None = None,
    ) -> ProfessorExtraction: ...


def run(
    config: Config,
    checkpoint: CheckpointStore,
    logger: logging.Logger,
    llm: ProfessorExtractor | None = None,
    *,
    limit: int | None = None,
    school_id: str | None = None,
    no_llm: bool = False,
    dry_run: bool = False,
) -> StageSummary:
    """Resumable per `profile_url`. `no_llm=True` runs the deterministic
    pass only (for debugging) and does not require an `llm` client;
    otherwise `llm` is required. `dry_run=True` reports how many profiles
    would be processed without making any LLM calls or writing anything.
    """
    if not no_llm and llm is None:
        raise ExtractError("extract requires an `llm` client unless no_llm=True")

    started_at = datetime.now(UTC)
    schools_by_id = _load_schools(config.data_dir)
    raw_profiles = _load_raw_profiles(config.data_dir)

    targets = [p for p in raw_profiles if school_id is None or p.school_id == school_id]
    eligible = [p for p in targets if not checkpoint.is_done(p.profile_url)]
    pending = eligible[:limit] if limit is not None else eligible
    skipped_already_done = len(targets) - len(eligible)

    if dry_run:
        return StageSummary(
            stage=STAGE_NAME,
            processed=0,
            skipped=skipped_already_done + len(pending),
            failed=0,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            notes=[f"[dry-run] would extract {len(pending)} profile(s); no LLM calls made"],
        )

    output_path = Path(config.data_dir) / "profiles_clean.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    processed = 0
    skipped = skipped_already_done
    failed = 0
    non_200 = 0
    non_profile = 0
    invalid_after_repair = 0

    with output_path.open("a", encoding="utf-8") as out:
        for raw in pending:
            school = schools_by_id.get(raw.school_id) or _fallback_school(raw.school_id)
            try:
                outcome = _extract_one(config, raw, school, llm, no_llm, logger)
            except ExtractionFailed as exc:
                invalid_after_repair += 1
                skipped += 1
                checkpoint.mark_done(
                    raw.profile_url, meta={"outcome": "invalid_after_repair", "error": str(exc)}
                )
                logger.warning(
                    "extract: invalid LLM response after repair retry: %s",
                    exc,
                    extra={"stage": STAGE_NAME, "school_id": raw.school_id, "url": raw.profile_url},
                )
                continue
            except Exception as exc:  # noqa: BLE001 - per-item failure, not fatal to the run
                failed += 1
                checkpoint.mark_failed(raw.profile_url, str(exc))
                logger.warning(
                    "extract failed: %s",
                    exc,
                    extra={"stage": STAGE_NAME, "school_id": raw.school_id, "url": raw.profile_url},
                )
                continue

            if outcome.kind == "extracted":
                assert outcome.professor is not None
                out.write(outcome.professor.model_dump_json())
                out.write("\n")
                out.flush()
                checkpoint.mark_done(raw.profile_url, meta={"outcome": "extracted"})
                processed += 1
                continue

            skipped += 1
            if outcome.kind == "non_200":
                non_200 += 1
            elif outcome.kind == "not_a_profile":
                non_profile += 1
            checkpoint.mark_done(raw.profile_url, meta={"outcome": outcome.kind})

    notes = [
        f"{processed} extracted, {non_200} non-200 (not a profile), "
        f"{non_profile} not-a-profile page(s), "
        f"{invalid_after_repair} invalid after repair retry"
    ]

    return StageSummary(
        stage=STAGE_NAME,
        processed=processed,
        skipped=skipped,
        failed=failed,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        notes=notes,
    )


# -- per-profile extraction -------------------------------------------------


@dataclass
class _ExtractOutcome:
    professor: Professor | None
    kind: Literal["extracted", "non_200", "not_a_profile", "no_name"]


def _extract_one(
    config: Config,
    raw: RawProfile,
    school: School,
    llm: ProfessorExtractor | None,
    no_llm: bool,
    logger: logging.Logger,
) -> _ExtractOutcome:
    if raw.http_status != 200:
        # A 404 (or any other non-200) is not a professor (M5 instructions):
        # never sent to the LLM, never becomes a row.
        return _ExtractOutcome(None, "non_200")

    html = Path(raw.html_cache_path).read_text(encoding="utf-8")
    text = _clean_text(html)
    hints = _deterministic_hints(html, raw.parse_hint)

    if no_llm:
        name = _best_deterministic_name(hints, school.name)
        if not name:
            return _ExtractOutcome(None, "no_name")
        professor = Professor(
            school_id=raw.school_id,
            school_name=school.name,
            professor_name=name,
            title=None,
            # No title to classify from, so the question stays open.
            is_faculty=None,
            department=hints.get("jsonld_department"),
            email=hints.get("email"),
            phone=hints.get("phone"),
            research_interests=None,
            profile_url=raw.profile_url,
            directory_url=raw.directory_url,
            extraction_confidence=_NO_LLM_CONFIDENCE,
            extracted_at=datetime.now(UTC),
        )
        return _ExtractOutcome(professor, "extracted")

    assert llm is not None
    extraction = llm.extract_professor(text, raw.profile_url, school, hints)

    name = extraction.get("professor_name")
    if not extraction.get("is_profile") or not name:
        return _ExtractOutcome(None, "not_a_profile")

    professor = Professor(
        school_id=raw.school_id,
        school_name=school.name,
        professor_name=_strip_boilerplate(name, school.name) or name,
        title=extraction.get("title"),
        is_faculty=_faculty_judgment(extraction.get("title"), extraction.get("is_faculty")),
        department=extraction.get("department"),
        email=_grounded_email(extraction.get("email"), text, hints),
        phone=_grounded_phone(extraction.get("phone"), text, hints),
        research_interests=extraction.get("research_interests"),
        profile_url=raw.profile_url,
        directory_url=raw.directory_url,
        extraction_confidence=_clamp01(extraction.get("confidence", 0.0)),
        extracted_at=datetime.now(UTC),
    )
    return _ExtractOutcome(professor, "extracted")


def _faculty_judgment(title: str | None, llm_says: Any) -> bool | None:
    """Is this person teaching faculty?

    The title is read deterministically first and wins where it is explicit,
    for the same reason `email` is grounded against the page: an academic
    rank written on the page is evidence, and the model's opinion is not. The
    model's answer is used only where the title says neither — which is also
    what happens for extractions cached before this field existed, since they
    simply have no `is_faculty` key.
    """
    from_title = classify_role(title)
    if from_title is not None:
        return from_title
    if isinstance(llm_says, bool):
        return llm_says
    return None


def _clamp01(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


# -- do-not-invent grounding (§6 Stage 4 / M5's deepest rule) ---------------


def _grounded_email(value: str | None, text: str, hints: dict[str, str | None]) -> str | None:
    """Keeps `value` only if it is a plausible email AND it is actually
    present on the page — either it matches the deterministic hint (pulled
    from the raw HTML: mailto:/JSON-LD/meta/de-obfuscated text) or it
    appears verbatim in the cleaned page text. An LLM-invented email,
    however plausible, is dropped rather than trusted."""
    if not value:
        return None
    candidate = value.strip()
    if not _EMAIL_RE.fullmatch(candidate):
        return None
    hint = hints.get("email")
    if hint and hint.lower() == candidate.lower():
        return candidate
    if candidate.lower() in text.lower():
        return candidate
    return None


def _grounded_phone(value: str | None, text: str, hints: dict[str, str | None]) -> str | None:
    """Digit-based grounding check (formatting varies too much across sites
    to require an exact string match): the phone's digits must match the
    deterministic hint's digits, or appear as a contiguous run within the
    page text's digits."""
    if not value:
        return None
    candidate = value.strip()
    digits = re.sub(r"\D", "", candidate)
    if len(digits) < 7:
        return None
    hint = hints.get("phone")
    hint_digits = re.sub(r"\D", "", hint) if hint else ""
    if hint_digits and hint_digits == digits:
        return candidate
    if digits in re.sub(r"\D", "", text):
        return candidate
    return None


def _strip_boilerplate(name: str | None, school_name: str) -> str | None:
    """Defense in depth against the `<title>`-derived trap this M5 build
    calls out by name: "Thalita Abrahao | Agnes Scott College". The prompt
    already tells the model not to do this, but a boilerplate suffix that
    matches (or is contained in) the school's own name is stripped here too,
    regardless of source."""
    if not name:
        return name
    for sep in _BOILERPLATE_SEPARATORS:
        if sep in name:
            head, _, tail = name.partition(sep)
            tail_norm = tail.strip().lower()
            school_norm = school_name.strip().lower()
            if tail_norm and (tail_norm == school_norm or tail_norm in school_norm
                               or school_norm in tail_norm):
                return head.strip() or None
    return name.strip() or None


# -- deterministic pass ------------------------------------------------------


def _clean_text(html: str) -> str:
    """Readable visible text of the page, noise chrome stripped, for the LLM
    prompt and for do-not-invent grounding checks."""
    tree = HTMLParser(html)
    for tag in _NOISE_TAGS:
        for node in tree.css(tag):
            node.decompose()
    body = tree.body if tree.body is not None else tree.root
    text = body.text(separator=" ") if body is not None else ""
    return " ".join(text.split())


def _deterministic_hints(html: str, parse_hint: dict[str, str | None]) -> dict[str, str | None]:
    """§6 Stage 4 deterministic pass: mailto:/tel: links, meta tags, JSON-LD
    `Person` blocks, and de-obfuscated/plain emails found in the visible
    text. Returned as a flat hints dict — both the evidence handed to the
    LLM (`services.llm._format_hints`) and the grounding set `_grounded_*`
    checks the LLM's answer against."""
    text = _clean_text(html)
    jsonld = _jsonld_person_hints(html)
    mailto = _first_mailto(html)
    tel = _first_tel(html)
    text_email = _email_from_text(text)
    meta_name = _meta_name(html)
    meta_author = _meta_author(html)

    email = jsonld.get("email") or mailto or text_email
    phone = jsonld.get("phone") or tel or _phone_from_text(text)

    return {
        "title_hint": parse_hint.get("name"),
        "title_hint_title": parse_hint.get("title"),
        "meta_name": meta_name,
        "meta_author": meta_author,
        "jsonld_name": jsonld.get("name"),
        "jsonld_title": jsonld.get("title"),
        "jsonld_department": jsonld.get("department"),
        "email": email,
        "phone": phone,
    }


def _best_deterministic_name(hints: dict[str, str | None], school_name: str) -> str | None:
    """Priority for `--no-llm` mode: JSON-LD `Person.name`, then
    `<meta name="author">`. Nothing else.

    The `<title>`/`<h1>` hint used to be third in this list, and on a real run
    that produced "Faculty Directory" 100 times, "Bard College" 39 times and
    "OneLogin" 20 times — page furniture and a login screen, filed as
    professors. A page title is not a claim about a person; JSON-LD `@type:
    Person` and a meta author tag are. Without an LLM to read the page, those
    two are the only evidence that names someone, so a page carrying neither
    yields no row at all. The hint still goes to the LLM, which can weigh it
    against the page text.
    """
    for key in ("jsonld_name", "meta_author"):
        value = hints.get(key)
        if value:
            stripped = _strip_boilerplate(value, school_name)
            if stripped:
                return stripped
    return None


def _meta_name(html: str) -> str | None:
    """Any page-level name-ish meta tag. A hint for the LLM only - `og:title`
    and `twitter:title` are titles of the *page*, so they can name a directory
    or a news article as easily as a person."""
    tree = HTMLParser(html)
    selectors = ('meta[property="og:title"]', 'meta[name="author"]', 'meta[name="twitter:title"]')
    for selector in selectors:
        node = tree.css_first(selector)
        if node is not None:
            content = node.attributes.get("content")
            if content and content.strip():
                return content.strip()
    return None


def _meta_author(html: str) -> str | None:
    """`<meta name="author">` only - the one meta tag that claims a person."""
    node = HTMLParser(html).css_first('meta[name="author"]')
    if node is None:
        return None
    content = node.attributes.get("content")
    return content.strip() if content and content.strip() else None


def _first_mailto(html: str) -> str | None:
    tree = HTMLParser(html)
    for node in tree.css("a[href]"):
        href = node.attributes.get("href") or ""
        if href.lower().startswith("mailto:"):
            addr = unquote(href[len("mailto:") :].split("?")[0].strip())
            if addr:
                return addr
    return None


def _first_tel(html: str) -> str | None:
    tree = HTMLParser(html)
    for node in tree.css("a[href]"):
        href = node.attributes.get("href") or ""
        if href.lower().startswith("tel:"):
            num = href[len("tel:") :].strip()
            if num:
                return num
    return None


def _email_from_text(text: str) -> str | None:
    """Plain emails written directly as text, plus the three de-obfuscation
    forms from §6 Stage 4 / M5: "name [at] domain.edu", "name (at) domain
    (dot) edu", "name AT domain DOT edu". All three reduce to the same
    literal-substitution-then-regex approach: normalize the obfuscation
    marker to '@'/'.' and search for a plain email in the result. A page
    with no obfuscation at all is unaffected by the substitutions and falls
    straight through to matching a plain address."""
    normalized = _BRACKET_AT_RE.sub("@", text)
    normalized = _BRACKET_DOT_RE.sub(".", normalized)
    normalized = _BARE_AT_RE.sub("@", normalized)
    normalized = _BARE_DOT_RE.sub(".", normalized)
    match = _EMAIL_RE.search(normalized)
    return match.group(0) if match else None


def _phone_from_text(text: str) -> str | None:
    match = _PHONE_RE.search(text)
    return match.group(0).strip() if match else None


def _jsonld_person_hints(html: str) -> dict[str, str | None]:
    tree = HTMLParser(html)
    for node in tree.css('script[type="application/ld+json"]'):
        raw = node.text()
        if not raw or not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for obj in _flatten_jsonld(data):
            if _is_jsonld_person(obj):
                return _person_fields(obj)
    return {}


def _flatten_jsonld(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        out: list[dict[str, Any]] = []
        for item in data:
            out.extend(_flatten_jsonld(item))
        return out
    if isinstance(data, dict):
        graph = data.get("@graph")
        if isinstance(graph, list):
            return _flatten_jsonld(graph)
        return [data]
    return []


def _is_jsonld_person(obj: dict[str, Any]) -> bool:
    type_ = obj.get("@type")
    if isinstance(type_, list):
        return "Person" in type_
    return type_ == "Person"


def _person_fields(obj: dict[str, Any]) -> dict[str, str | None]:
    name = _as_str(obj.get("name"))
    title = _as_str(obj.get("jobTitle"))
    department = None
    affiliation = obj.get("worksFor") or obj.get("affiliation")
    if isinstance(affiliation, dict):
        department = _as_str(affiliation.get("name"))
    elif isinstance(affiliation, str):
        department = affiliation.strip() or None
    email = _as_str(obj.get("email"))
    if email and email.lower().startswith("mailto:"):
        email = email[len("mailto:") :].strip() or None
    phone = _as_str(obj.get("telephone"))
    return {"name": name, "title": title, "department": department, "email": email, "phone": phone}


def _as_str(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


# -- loading ------------------------------------------------------------


def _fallback_school(school_id: str) -> School:
    """A school_id present in `profiles_raw.jsonl` but missing from
    `schools.jsonl` (e.g. a hand-run `crawl --school` against a school
    Stage 1 hasn't (re)loaded) shouldn't abort the whole extract run — the
    LLM prompt still works with just the id standing in for the name."""
    return School(school_id=school_id, name=school_id, slug=school_id, country="US", homepage="")


def _load_schools(data_dir: str | Path) -> dict[str, School]:
    path = Path(data_dir) / "schools.jsonl"
    if not path.exists():
        return {}
    schools: dict[str, School] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            school = School.model_validate_json(line)
            schools[school.school_id] = school
    return schools


def _load_raw_profiles(data_dir: str | Path) -> list[RawProfile]:
    path = Path(data_dir) / "profiles_raw.jsonl"
    if not path.exists():
        raise ExtractError(
            f"raw profiles not found at {path}. Run `python -m faculty_pipeline crawl` first."
        )
    profiles: list[RawProfile] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            profiles.append(RawProfile.model_validate_json(line))
    return profiles
