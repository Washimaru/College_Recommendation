from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from faculty_pipeline.config import Config
from faculty_pipeline.models import Professor, RawProfile, School
from faculty_pipeline.services.checkpoint import CheckpointStore
from faculty_pipeline.services.llm import ExtractionFailed, ProfessorExtraction
from faculty_pipeline.stages import extract

FIXTURES = Path(__file__).parent / "fixtures" / "extract"
CRAWL_FIXTURES = Path(__file__).parent / "fixtures" / "crawl"

logger = logging.getLogger("test")


# -- test helpers -------------------------------------------------------


def _fixture_path(name: str, crawl: bool = False) -> str:
    base = CRAWL_FIXTURES if crawl else FIXTURES
    return str(base / name)


def _config(tmp_path: Path) -> Config:
    return Config(
        input_path=tmp_path / "schools.json",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        checkpoint_dir=tmp_path / "checkpoints",
        log_dir=tmp_path / "logs",
    )


def _school(school_id: str = "acme-college", name: str = "Acme College") -> School:
    return School(
        school_id=school_id,
        name=name,
        slug=school_id,
        country="US",
        homepage="https://www.acmecollege.edu",
    )


def _write_schools(config: Config, schools: list[School]) -> None:
    path = Path(config.data_dir) / "schools.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(s.model_dump_json() for s in schools) + "\n", encoding="utf-8")


def _raw_profile(
    *,
    school_id: str = "acme-college",
    profile_url: str = "https://www.acmecollege.edu/faculty/jane-doe",
    html_cache_path: str,
    http_status: int = 200,
    parse_hint: dict | None = None,
) -> RawProfile:
    return RawProfile(
        school_id=school_id,
        profile_url=profile_url,
        directory_url="https://www.acmecollege.edu/faculty",
        html_cache_path=html_cache_path,
        fetched_at=datetime.now(UTC),
        http_status=http_status,
        parse_hint=parse_hint or {},
    )


def _write_raw_profiles(config: Config, profiles: list[RawProfile]) -> None:
    path = Path(config.data_dir) / "profiles_raw.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(p.model_dump_json() for p in profiles) + "\n", encoding="utf-8")


def _read_clean(config: Config) -> list[Professor]:
    path = Path(config.data_dir) / "profiles_clean.jsonl"
    if not path.exists():
        return []
    return [
        Professor.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class FakeLLM:
    """A canned `ProfessorExtractor` — one `ProfessorExtraction` per call,
    consumed in order, or a fixed response for every call."""

    def __init__(
        self,
        responses: list[ProfessorExtraction] | None = None,
        response: ProfessorExtraction | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._responses = list(responses) if responses is not None else None
        self._response = response
        self._exc = exc
        self.calls: list[tuple[str, str, School, dict]] = []

    def extract_professor(self, text, url, school, hints=None):  # noqa: ANN001
        self.calls.append((text, url, school, hints or {}))
        if self._exc is not None:
            raise self._exc
        if self._responses is not None:
            return self._responses.pop(0)
        assert self._response is not None
        return self._response


def _extraction(**overrides: object) -> ProfessorExtraction:
    defaults: dict[str, object] = dict(
        is_profile=True,
        professor_name="Jane Doe",
        title="Professor of Biology",
        department="Biology",
        email=None,
        phone=None,
        research_interests="genomics; evolutionary biology",
        confidence=0.9,
        notes="",
    )
    defaults.update(overrides)
    return ProfessorExtraction(defaults)


def _not_a_profile(notes: str = "directory index, not a person") -> ProfessorExtraction:
    return ProfessorExtraction(
        is_profile=False,
        professor_name=None,
        title=None,
        department=None,
        email=None,
        phone=None,
        research_interests=None,
        confidence=0.0,
        notes=notes,
    )


# -- deterministic pass ---------------------------------------------------


def test_jsonld_person_block_is_extracted() -> None:
    html = (FIXTURES / "profile_jsonld.html").read_text(encoding="utf-8")
    hints = extract._deterministic_hints(html, {})

    assert hints["jsonld_name"] == "Priya Natarajan"
    assert hints["jsonld_title"] == "Associate Professor of Physics"
    assert hints["jsonld_department"] == "Department of Physics"
    assert hints["email"] == "pnatarajan@acmecollege.edu"
    assert hints["phone"] == "555-201-3344"


def test_email_deobfuscation_bracket_at_dot(tmp_path: Path) -> None:
    # tests/fixtures/crawl/profile_jane_doe.html uses "jane.doe [at] acmecollege.edu"
    html = (CRAWL_FIXTURES / "profile_jane_doe.html").read_text(encoding="utf-8")
    hints = extract._deterministic_hints(html, {})
    assert hints["email"] == "jane.doe@acmecollege.edu"


def test_email_deobfuscation_paren_at_paren_dot() -> None:
    html = (FIXTURES / "profile_email_paren.html").read_text(encoding="utf-8")
    hints = extract._deterministic_hints(html, {})
    assert hints["email"] == "carlos.diaz@acmecollege.edu"


def test_email_deobfuscation_bare_at_dot() -> None:
    html = (FIXTURES / "profile_email_bare.html").read_text(encoding="utf-8")
    hints = extract._deterministic_hints(html, {})
    assert hints["email"] == "emily.zhou@acmecollege.edu"


def test_plain_email_and_phone_found_directly_in_text() -> None:
    html = (FIXTURES / "profile_plain_email.html").read_text(encoding="utf-8")
    hints = extract._deterministic_hints(html, {})
    assert hints["email"] == "nkim@acmecollege.edu"
    assert hints["phone"] == "404.471.6163"


def test_bare_at_dot_does_not_false_positive_on_ordinary_prose() -> None:
    # "look AT the DOT" is not an email pattern the marker regex should
    # accidentally assemble into one.
    text = "Meet me at the department; look AT the big DOT on the campus map."
    assert extract._email_from_text(text) is None


def test_title_hint_boilerplate_is_stripped_for_deterministic_name() -> None:
    hints = {
        "title_hint": "Thalita Abrahao | Agnes Scott College",
        "meta_name": None,
        "jsonld_name": None,
    }
    name = extract._best_deterministic_name(hints, "Agnes Scott College")
    assert name == "Thalita Abrahao"


def test_meta_og_title_preferred_over_boilerplate_title_hint() -> None:
    hints = {
        "title_hint": "Thalita Abrahao | Agnes Scott College",
        "meta_name": "Thalita Abrahao",
        "jsonld_name": None,
    }
    assert extract._best_deterministic_name(hints, "Agnes Scott College") == "Thalita Abrahao"


def test_strip_boilerplate_leaves_unrelated_names_alone() -> None:
    # A hyphenated surname must not be mistaken for a boilerplate separator.
    assert extract._strip_boilerplate("Mary-Jane Watson", "Acme College") == "Mary-Jane Watson"


# -- run(): non-200, not-a-profile, no-name, checkpointing -----------------


def test_non_200_profile_yields_no_row(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_schools(config, [_school()])
    raw = _raw_profile(html_cache_path=_fixture_path("profile_not_found.html"), http_status=404)
    _write_raw_profiles(config, [raw])
    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / "extract.json")
    llm = FakeLLM()

    summary = extract.run(config, checkpoint, logger, llm)

    assert summary.processed == 0
    assert summary.skipped == 1
    assert llm.calls == []  # a 404 is never sent to the LLM
    assert _read_clean(config) == []
    assert checkpoint.is_done(raw.profile_url)


def test_llm_flagged_non_profile_page_yields_no_row(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_schools(config, [_school()])
    raw = _raw_profile(html_cache_path=_fixture_path("directory_index.html", crawl=True))
    _write_raw_profiles(config, [raw])
    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / "extract.json")
    llm = FakeLLM(response=_not_a_profile())

    summary = extract.run(config, checkpoint, logger, llm)

    assert summary.processed == 0
    assert summary.skipped == 1
    assert _read_clean(config) == []
    assert checkpoint.is_done(raw.profile_url)


def test_missing_professor_name_yields_no_row(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_schools(config, [_school()])
    raw = _raw_profile(html_cache_path=_fixture_path("profile_plain_email.html"))
    _write_raw_profiles(config, [raw])
    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / "extract.json")
    # A malformed-but-coerced response: is_profile true, no name.
    llm = FakeLLM(response=_extraction(professor_name=None))

    summary = extract.run(config, checkpoint, logger, llm)

    assert summary.processed == 0
    assert _read_clean(config) == []


def test_already_done_profiles_are_skipped_without_calling_llm(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_schools(config, [_school()])
    raw = _raw_profile(html_cache_path=_fixture_path("profile_jsonld.html"))
    _write_raw_profiles(config, [raw])
    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / "extract.json")
    checkpoint.mark_done(raw.profile_url)
    llm = FakeLLM(response=_extraction())

    summary = extract.run(config, checkpoint, logger, llm)

    assert summary.processed == 0
    assert summary.skipped == 1
    assert llm.calls == []


def test_limit_bounds_the_number_of_profiles_processed(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_schools(config, [_school()])
    profiles = [
        _raw_profile(
            profile_url=f"https://www.acmecollege.edu/faculty/p{i}",
            html_cache_path=_fixture_path("profile_jsonld.html"),
        )
        for i in range(3)
    ]
    _write_raw_profiles(config, profiles)
    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / "extract.json")
    llm = FakeLLM(response=_extraction())

    summary = extract.run(config, checkpoint, logger, llm, limit=2)

    assert summary.processed == 2
    assert len(llm.calls) == 2


def test_school_id_filters_to_one_school(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_schools(config, [_school("acme-college", "Acme College"), _school("other", "Other U")])
    profiles = [
        _raw_profile(
            school_id="acme-college",
            profile_url="https://www.acmecollege.edu/faculty/a",
            html_cache_path=_fixture_path("profile_jsonld.html"),
        ),
        _raw_profile(
            school_id="other",
            profile_url="https://www.other.edu/faculty/b",
            html_cache_path=_fixture_path("profile_jsonld.html"),
        ),
    ]
    _write_raw_profiles(config, profiles)
    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / "extract.json")
    llm = FakeLLM(response=_extraction())

    summary = extract.run(config, checkpoint, logger, llm, school_id="acme-college")

    assert summary.processed == 1
    assert len(llm.calls) == 1


def test_missing_raw_profiles_file_raises_extract_error(tmp_path: Path) -> None:
    config = _config(tmp_path)
    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / "extract.json")

    with pytest.raises(extract.ExtractError):
        extract.run(config, checkpoint, logger, FakeLLM())


def test_dry_run_makes_no_llm_calls_and_writes_nothing(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_schools(config, [_school()])
    raw = _raw_profile(html_cache_path=_fixture_path("profile_jsonld.html"))
    _write_raw_profiles(config, [raw])
    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / "extract.json")
    llm = FakeLLM(response=_extraction())

    summary = extract.run(config, checkpoint, logger, llm, dry_run=True)

    assert llm.calls == []
    assert not (Path(config.data_dir) / "profiles_clean.jsonl").exists()
    assert not checkpoint.is_done(raw.profile_url)
    assert summary.notes[0].startswith("[dry-run]")


# -- do-not-invent: email/phone grounding -----------------------------------


def test_llm_invented_email_not_grounded_in_page_is_dropped(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_schools(config, [_school()])
    # This page has no email anywhere in it or in deterministic hints.
    raw = _raw_profile(html_cache_path=_fixture_path("profile_not_found.html"), http_status=200)
    _write_raw_profiles(config, [raw])
    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / "extract.json")
    llm = FakeLLM(response=_extraction(email="totally.invented@nowhere.example"))

    extract.run(config, checkpoint, logger, llm)

    rows = _read_clean(config)
    assert len(rows) == 1
    assert rows[0].email is None


def test_llm_email_grounded_in_page_text_is_kept(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_schools(config, [_school()])
    raw = _raw_profile(html_cache_path=_fixture_path("profile_plain_email.html"))
    _write_raw_profiles(config, [raw])
    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / "extract.json")
    llm = FakeLLM(response=_extraction(email="nkim@acmecollege.edu"))

    extract.run(config, checkpoint, logger, llm)

    rows = _read_clean(config)
    assert rows[0].email == "nkim@acmecollege.edu"


def test_llm_email_grounded_only_via_mailto_hint_is_kept(tmp_path: Path) -> None:
    # profile_mailto_only.html's link text is "Contact", not the address
    # itself, so the email is only recoverable from the mailto: href (the
    # deterministic hint) - not from a literal substring of the visible
    # text. Grounding via the hint alone must still be honored.
    config = _config(tmp_path)
    _write_schools(config, [_school()])
    raw = _raw_profile(html_cache_path=_fixture_path("profile_mailto_only.html"))
    _write_raw_profiles(config, [raw])
    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / "extract.json")
    llm = FakeLLM(response=_extraction(email="pnatarajan@acmecollege.edu"))

    extract.run(config, checkpoint, logger, llm)

    rows = _read_clean(config)
    assert rows[0].email == "pnatarajan@acmecollege.edu"


def test_llm_invented_phone_not_grounded_is_dropped(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_schools(config, [_school()])
    raw = _raw_profile(html_cache_path=_fixture_path("profile_not_found.html"))
    _write_raw_profiles(config, [raw])
    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / "extract.json")
    llm = FakeLLM(response=_extraction(phone="555-000-1234"))

    extract.run(config, checkpoint, logger, llm)

    rows = _read_clean(config)
    assert rows[0].phone is None


def test_llm_grounded_phone_with_different_formatting_is_kept(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_schools(config, [_school()])
    raw = _raw_profile(html_cache_path=_fixture_path("profile_plain_email.html"))
    _write_raw_profiles(config, [raw])
    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / "extract.json")
    # Page text has "404.471.6163"; LLM reformats it with different punctuation.
    llm = FakeLLM(response=_extraction(phone="(404) 471-6163"))

    extract.run(config, checkpoint, logger, llm)

    rows = _read_clean(config)
    assert rows[0].phone == "(404) 471-6163"


def test_professor_name_boilerplate_is_stripped_even_from_llm_output(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_schools(config, [_school("agnes-scott-college", "Agnes Scott College")])
    raw = _raw_profile(
        school_id="agnes-scott-college",
        html_cache_path=_fixture_path("profile_jsonld.html"),
        parse_hint={"name": "Thalita Abrahao | Agnes Scott College", "title": None},
    )
    _write_raw_profiles(config, [raw])
    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / "extract.json")
    # Simulate the LLM failing to strip boilerplate despite instructions.
    llm = FakeLLM(response=_extraction(professor_name="Thalita Abrahao | Agnes Scott College"))

    extract.run(config, checkpoint, logger, llm)

    rows = _read_clean(config)
    assert rows[0].professor_name == "Thalita Abrahao"


# -- --no-llm ---------------------------------------------------------------


def test_no_llm_mode_uses_deterministic_pass_only(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_schools(config, [_school()])
    raw = _raw_profile(html_cache_path=_fixture_path("profile_jsonld.html"))
    _write_raw_profiles(config, [raw])
    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / "extract.json")

    summary = extract.run(config, checkpoint, logger, llm=None, no_llm=True)

    assert summary.processed == 1
    rows = _read_clean(config)
    assert rows[0].professor_name == "Priya Natarajan"
    assert rows[0].email == "pnatarajan@acmecollege.edu"
    assert rows[0].extraction_confidence == extract._NO_LLM_CONFIDENCE


def test_no_llm_mode_skips_profile_with_no_determinable_name(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_schools(config, [_school()])
    raw = _raw_profile(
        html_cache_path=_fixture_path("directory_index.html", crawl=True),
        parse_hint={},
    )
    _write_raw_profiles(config, [raw])
    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / "extract.json")

    summary = extract.run(config, checkpoint, logger, llm=None, no_llm=True)

    assert summary.processed == 0
    assert _read_clean(config) == []


def test_no_llm_true_without_llm_client_does_not_require_one(tmp_path: Path) -> None:
    config = _config(tmp_path)
    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / "extract.json")
    _write_raw_profiles(config, [])
    # Should not raise ExtractError about a missing llm client.
    summary = extract.run(config, checkpoint, logger, llm=None, no_llm=True)
    assert summary.processed == 0


def test_llm_required_when_no_llm_false_and_client_missing(tmp_path: Path) -> None:
    config = _config(tmp_path)
    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / "extract.json")
    _write_raw_profiles(config, [])
    with pytest.raises(extract.ExtractError):
        extract.run(config, checkpoint, logger, llm=None, no_llm=False)


# -- invalid-after-repair-retry propagation ----------------------------------


def test_extraction_failed_is_skipped_and_marked_done_not_failed(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_schools(config, [_school()])
    raw = _raw_profile(html_cache_path=_fixture_path("profile_jsonld.html"))
    _write_raw_profiles(config, [raw])
    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / "extract.json")
    llm = FakeLLM(exc=ExtractionFailed("invalid response after one repair retry: boom"))

    summary = extract.run(config, checkpoint, logger, llm)

    assert summary.processed == 0
    assert summary.failed == 0
    assert summary.skipped == 1
    assert checkpoint.is_done(raw.profile_url)  # skipped, not left for retry


def test_generic_llm_error_marks_failed_for_retry(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_schools(config, [_school()])
    raw = _raw_profile(html_cache_path=_fixture_path("profile_jsonld.html"))
    _write_raw_profiles(config, [raw])
    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / "extract.json")
    llm = FakeLLM(exc=RuntimeError("connection reset"))

    summary = extract.run(config, checkpoint, logger, llm)

    assert summary.failed == 1
    assert not checkpoint.is_done(raw.profile_url)
    entry = checkpoint.entry(raw.profile_url)
    assert entry is not None and entry.status == "failed"
