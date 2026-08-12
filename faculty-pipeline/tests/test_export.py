from __future__ import annotations

import csv
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from faculty_pipeline.config import Config
from faculty_pipeline.models import Professor
from faculty_pipeline.services.checkpoint import CheckpointStore
from faculty_pipeline.stages import export

logger = logging.getLogger("test")


# -- test helpers -------------------------------------------------------


def _config(tmp_path: Path, **overrides: object) -> Config:
    return Config(
        input_path=tmp_path / "schools.json",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        checkpoint_dir=tmp_path / "checkpoints",
        log_dir=tmp_path / "logs",
        output_dir=tmp_path / "output",
        **overrides,
    )


def _checkpoint(config: Config) -> CheckpointStore:
    return CheckpointStore(Path(config.checkpoint_dir) / "export.json")


def _professor(
    *,
    school_id: str = "acme-college",
    school_name: str = "Acme College",
    professor_name: str = "Jane Doe",
    title: str | None = "Professor",
    department: str | None = "Biology",
    email: str | None = "jane.doe@acme.edu",
    phone: str | None = None,
    research_interests: str | None = "genetics; ecology",
    profile_url: str = "https://www.acme.edu/faculty/jane-doe",
    directory_url: str = "https://www.acme.edu/faculty",
    extraction_confidence: float = 0.9,
    extracted_at: datetime = datetime(2026, 8, 4, 18, 22, 10, tzinfo=UTC),
) -> Professor:
    return Professor(
        school_id=school_id,
        school_name=school_name,
        professor_name=professor_name,
        title=title,
        department=department,
        email=email,
        phone=phone,
        research_interests=research_interests,
        profile_url=profile_url,
        directory_url=directory_url,
        extraction_confidence=extraction_confidence,
        extracted_at=extracted_at,
    )


def _write_clean(config: Config, professors: list[Professor]) -> None:
    path = Path(config.data_dir) / "profiles_clean.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(p.model_dump_json() for p in professors) + ("\n" if professors else ""),
        encoding="utf-8",
    )


def _write_raw(config: Config, rows: list[dict[str, object]]) -> None:
    path = Path(config.data_dir) / "profiles_raw.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r) for r in rows) + ("\n" if rows else ""), encoding="utf-8"
    )


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# Verbatim from tests/test_crawl.py's real Bard capture: 17 profiles, every
# surname under A, from the first live run.
_BARD_PARTIAL_SLUGS = (
    "susan-aberth", "ziad-abu-rish", "kenyon-adams", "ross-exo-adams",
    "folarin-ajibade", "jasmine-akiyama-kim", "kathryn-aldous",
    "richard-aldous", "jaime-osterman-alves", "craig-anderson",
    "sven-anderson", "victor-apryshchenko", "nathanael-aschenbrenner",
    "ephraim-asili", "andrew-atwell", "erin-atwell", "jordan-ayala",
)  # fmt: skip


def _bard_professors() -> list[Professor]:
    return [
        _professor(
            school_id="bard-college",
            school_name="Bard College",
            professor_name=slug.replace("-", " ").title(),
            profile_url=f"https://www.bard.edu/faculty/{slug}",
            directory_url="https://www.bard.edu/faculty/",
        )
        for slug in _BARD_PARTIAL_SLUGS
    ]


# -- column order & UTF-8 -------------------------------------------------


def test_csv_columns_are_in_exact_section_4_4_order(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_clean(config, [_professor()])

    export.run(config, _checkpoint(config), logger)

    with (Path(config.output_dir) / "master.csv").open(encoding="utf-8") as f:
        header = next(csv.reader(f))

    assert header == [
        "school_id",
        "school_name",
        "professor_name",
        "title",
        # Added when the exporter learned to tell faculty from administrators;
        # docs/FACULTY_PIPELINE.md §4.4 moved with it.
        "is_faculty",
        "department",
        "email",
        "phone",
        "research_interests",
        "profile_url",
        "directory_url",
        "extraction_confidence",
        "extracted_at",
    ]


def test_diacritic_name_round_trips_as_utf8(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_clean(config, [_professor(professor_name="María José Peña")])

    export.run(config, _checkpoint(config), logger)

    rows = _read_csv(Path(config.output_dir) / "master.csv")
    assert rows[0]["professor_name"] == "María José Peña"
    # Bytes on disk are UTF-8, not escaped/mangled.
    raw_bytes = (Path(config.output_dir) / "master.csv").read_bytes()
    assert "María José Peña".encode() in raw_bytes


# -- the null-not-"None" rule -----------------------------------------------


def test_none_fields_become_empty_cells_never_the_string_none(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_clean(
        config,
        [_professor(title=None, department=None, email=None, phone=None, research_interests=None)],
    )

    export.run(config, _checkpoint(config), logger)

    rows = _read_csv(Path(config.output_dir) / "master.csv")
    row = rows[0]
    for column in ("title", "department", "email", "phone", "research_interests"):
        assert row[column] == "", f"{column} was {row[column]!r}"
    # The specific strings a naive f-string or pandas round-trip would produce.
    raw_text = (Path(config.output_dir) / "master.csv").read_text(encoding="utf-8")
    for bad in ("None", "null", "NaN", "nan"):
        assert bad not in raw_text


# -- confidence filtering ----------------------------------------------------


def test_rows_below_min_confidence_are_excluded_from_csvs(tmp_path: Path) -> None:
    config = _config(tmp_path, min_confidence=0.5)
    kept = _professor(professor_name="Above Floor", extraction_confidence=0.6)
    dropped = _professor(professor_name="Below Floor", extraction_confidence=0.4)
    _write_clean(config, [kept, dropped])

    summary = export.run(config, _checkpoint(config), logger)

    rows = _read_csv(Path(config.output_dir) / "master.csv")
    names = {r["professor_name"] for r in rows}
    assert names == {"Above Floor"}
    assert summary.processed == 1
    assert summary.skipped == 1


def test_confidence_threshold_is_inclusive(tmp_path: Path) -> None:
    config = _config(tmp_path, min_confidence=0.5)
    _write_clean(config, [_professor(professor_name="Exactly At Floor", extraction_confidence=0.5)])

    export.run(config, _checkpoint(config), logger)

    rows = _read_csv(Path(config.output_dir) / "master.csv")
    assert [r["professor_name"] for r in rows] == ["Exactly At Floor"]


def test_school_with_all_rows_below_floor_gets_no_csv(tmp_path: Path) -> None:
    config = _config(tmp_path, min_confidence=0.5)
    _write_clean(
        config,
        [_professor(school_id="low-conf-college", extraction_confidence=0.1)],
    )

    export.run(config, _checkpoint(config), logger)

    assert not (Path(config.output_dir) / "by_school" / "low-conf-college.csv").exists()
    coverage = _read_csv(Path(config.output_dir) / "coverage.csv")
    assert coverage[0]["professors_in_csv"] == "0"
    assert coverage[0]["professors_below_confidence"] == "1"


# -- per-school grouping & master = union -----------------------------------


def test_per_school_csvs_and_master_are_the_union(tmp_path: Path) -> None:
    config = _config(tmp_path)
    mit = _professor(school_id="mit", school_name="MIT", professor_name="Alice A")
    reed = _professor(school_id="reed-college", school_name="Reed College", professor_name="Bob B")
    _write_clean(config, [mit, reed])

    export.run(config, _checkpoint(config), logger)

    mit_rows = _read_csv(Path(config.output_dir) / "by_school" / "mit.csv")
    reed_rows = _read_csv(Path(config.output_dir) / "by_school" / "reed-college.csv")
    master_rows = _read_csv(Path(config.output_dir) / "master.csv")

    assert [r["professor_name"] for r in mit_rows] == ["Alice A"]
    assert [r["professor_name"] for r in reed_rows] == ["Bob B"]
    assert len(master_rows) == len(mit_rows) + len(reed_rows)
    assert {r["professor_name"] for r in master_rows} == {"Alice A", "Bob B"}
    # Identical columns across per-school and master CSVs.
    with (Path(config.output_dir) / "by_school" / "mit.csv").open(encoding="utf-8") as f:
        mit_header = next(csv.reader(f))
    with (Path(config.output_dir) / "master.csv").open(encoding="utf-8") as f:
        master_header = next(csv.reader(f))
    assert mit_header == master_header


# -- partial-coverage (alphabetical) detection -------------------------------


def test_bard_style_alphabetical_partial_is_flagged_in_coverage(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_clean(config, _bard_professors())

    summary = export.run(config, _checkpoint(config), logger)

    coverage = _read_csv(Path(config.output_dir) / "coverage.csv")
    row = next(r for r in coverage if r["school_id"] == "bard-college")
    assert row["partial_coverage"] == "true"
    assert row["incomplete"] == "true"
    assert any("PARTIAL" in note for note in summary.notes)
    assert any("1 of 1" in note for note in summary.notes)
    # The school's CSV is still written in full, not thrown away.
    bard_rows = _read_csv(Path(config.output_dir) / "by_school" / "bard-college.csv")
    assert len(bard_rows) == 17


def test_a_spread_of_surnames_is_not_flagged_partial(tmp_path: Path) -> None:
    config = _config(tmp_path)
    # firstname-surname slugs, both sides varied — real-shaped, unlike a
    # shared literal prefix which would itself read as concentrated.
    slugs = (
        "susan-aberth", "john-brown", "amy-chen", "raj-desai", "li-evans",
        "omar-farouk", "gita-ghosh", "hans-iqbal", "ines-jansen",
    )  # fmt: skip
    professors = [
        _professor(
            school_id="wide-college",
            professor_name=slug.replace("-", " ").title(),
            profile_url=f"https://x.edu/faculty/{slug}",
        )
        for slug in slugs
    ]
    _write_clean(config, professors)

    export.run(config, _checkpoint(config), logger)

    coverage = _read_csv(Path(config.output_dir) / "coverage.csv")
    row = next(r for r in coverage if r["school_id"] == "wide-college")
    assert row["partial_coverage"] == "false"
    assert row["incomplete"] == "false"


# -- capped_at_limit (max_profiles_per_school truncation) --------------------


def test_school_at_the_profile_cap_is_flagged_capped(tmp_path: Path) -> None:
    config = _config(tmp_path, max_profiles_per_school=3)
    _write_clean(
        config,
        [_professor(school_id="capped-college", professor_name=f"Person {i}") for i in range(2)],
    )
    _write_raw(
        config,
        [
            {"school_id": "capped-college", "profile_url": f"https://x.edu/faculty/{i}"}
            for i in range(3)  # == max_profiles_per_school
        ],
    )

    summary = export.run(config, _checkpoint(config), logger)

    coverage = _read_csv(Path(config.output_dir) / "coverage.csv")
    row = next(r for r in coverage if r["school_id"] == "capped-college")
    assert row["capped_at_limit"] == "true"
    assert row["incomplete"] == "true"
    assert any("CAPPED" in note for note in summary.notes)


def test_school_under_the_profile_cap_is_not_flagged_capped(tmp_path: Path) -> None:
    config = _config(tmp_path, max_profiles_per_school=100)
    _write_clean(config, [_professor(school_id="small-college")])
    _write_raw(
        config, [{"school_id": "small-college", "profile_url": "https://x.edu/faculty/a"}]
    )

    export.run(config, _checkpoint(config), logger)

    coverage = _read_csv(Path(config.output_dir) / "coverage.csv")
    row = next(r for r in coverage if r["school_id"] == "small-college")
    assert row["capped_at_limit"] == "false"


def test_capped_at_limit_is_unknown_when_raw_profiles_missing(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_clean(config, [_professor(school_id="acme-college")])
    # No data/profiles_raw.jsonl written at all.

    summary = export.run(config, _checkpoint(config), logger)

    coverage = _read_csv(Path(config.output_dir) / "coverage.csv")
    row = next(r for r in coverage if r["school_id"] == "acme-college")
    assert row["capped_at_limit"] == "unknown"
    assert any("profiles_raw.jsonl not found" in note for note in summary.notes)


# -- the plain "how many schools are incomplete" summary ---------------------


def test_summary_states_incomplete_count_even_when_zero(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_clean(config, [_professor()])
    _write_raw(config, [{"school_id": "acme-college", "profile_url": "https://x.edu/a"}])

    summary = export.run(config, _checkpoint(config), logger)

    assert any("0 of 1 school(s)" in note and "incomplete" in note for note in summary.notes)


# -- malformed rows -----------------------------------------------------------


def test_malformed_jsonl_line_is_skipped_not_fatal(tmp_path: Path) -> None:
    config = _config(tmp_path)
    path = Path(config.data_dir) / "profiles_clean.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        _professor().model_dump_json() + "\n" + "{not valid json\n", encoding="utf-8"
    )

    summary = export.run(config, _checkpoint(config), logger)

    assert summary.failed == 1
    assert summary.processed == 1


# -- missing input ------------------------------------------------------------


def test_missing_clean_profiles_raises_actionable_error(tmp_path: Path) -> None:
    config = _config(tmp_path)

    try:
        export.run(config, _checkpoint(config), logger)
        raised = False
    except export.ExportError as exc:
        raised = True
        assert "extract" in str(exc)
    assert raised


# -- dry run -------------------------------------------------------------


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_clean(config, [_professor()])

    summary = export.run(config, _checkpoint(config), logger, dry_run=True)

    assert not Path(config.output_dir).exists() or not any(Path(config.output_dir).iterdir())
    assert summary.processed == 0
    assert any("dry-run" in note for note in summary.notes)


def test_dry_run_reports_would_be_counts(tmp_path: Path) -> None:
    config = _config(tmp_path, min_confidence=0.5)
    _write_clean(
        config,
        [
            _professor(professor_name="Kept", extraction_confidence=0.9),
            _professor(professor_name="Dropped", extraction_confidence=0.1),
        ],
    )

    summary = export.run(config, _checkpoint(config), logger, dry_run=True)

    assert any("1 row(s)" in note or "would write" in note for note in summary.notes)
    assert summary.skipped == 2  # both counted, since nothing was actually written


# -- golden CSV (§11) ---------------------------------------------------------


def test_golden_master_csv(tmp_path: Path) -> None:
    """A small, fully fixed input asserts an exact master.csv byte-for-byte
    (minus the header, which is asserted separately above) — §11."""
    config = _config(tmp_path, min_confidence=0.5)
    professors = [
        Professor(
            school_id="agnes-scott-college",
            school_name="Agnes Scott College",
            professor_name="Charlotte Artese",
            title="Professor of English",
            department="English",
            email="cartese@agnesscott.edu",
            phone=None,
            research_interests="Shakespeare; early modern drama",
            profile_url="https://www.agnesscott.edu/english/artese.html",
            directory_url="https://www.agnesscott.edu/english/",
            extraction_confidence=0.98,
            extracted_at=datetime(2026, 8, 4, 18, 22, 10, tzinfo=UTC),
        ),
        Professor(
            school_id="agnes-scott-college",
            school_name="Agnes Scott College",
            professor_name="Thalita Abrahao",
            title=None,
            department=None,
            email=None,
            phone=None,
            research_interests=None,
            profile_url="https://www.agnesscott.edu/faculty/abrahao.html",
            directory_url="https://www.agnesscott.edu/faculty/",
            extraction_confidence=0.95,
            extracted_at=datetime(2026, 8, 4, 18, 22, 10, tzinfo=UTC),
        ),
        Professor(
            school_id="reed-college",
            school_name="Reed College",
            professor_name="Low Confidence Person",
            title=None,
            department=None,
            email=None,
            phone=None,
            research_interests=None,
            profile_url="https://www.reed.edu/faculty/lowconf.html",
            directory_url="https://www.reed.edu/faculty/",
            extraction_confidence=0.2,
            extracted_at=datetime(2026, 8, 4, 18, 22, 10, tzinfo=UTC),
        ),
    ]
    _write_clean(config, professors)

    export.run(config, _checkpoint(config), logger)

    # read_text() normalizes line endings; the golden file is checked against
    # csv.writer's logical rows, not its raw \r\n bytes.
    actual = (Path(config.output_dir) / "master.csv").read_text(encoding="utf-8")
    expected = (
        "school_id,school_name,professor_name,title,is_faculty,department,email,phone,"
        "research_interests,profile_url,directory_url,extraction_confidence,extracted_at\n"
        "agnes-scott-college,Agnes Scott College,Charlotte Artese,Professor of English,"
        "true,English,cartese@agnesscott.edu,,Shakespeare; early modern drama,"
        "https://www.agnesscott.edu/english/artese.html,"
        "https://www.agnesscott.edu/english/,0.98,2026-08-04T18:22:10+00:00\n"
        "agnes-scott-college,Agnes Scott College,Thalita Abrahao,,,,,,,"
        "https://www.agnesscott.edu/faculty/abrahao.html,"
        "https://www.agnesscott.edu/faculty/,0.95,2026-08-04T18:22:10+00:00\n"
    )
    assert actual == expected


# -- faculty vs staff ---------------------------------------------------


class TestNonFacultyRows:
    """A named administrator on a `/people/` page is a real extraction and a
    real person — but not a professor. Rows classified as staff stay in the
    JSONL for audit and are left out of the CSVs, counted rather than
    silently dropped."""

    def test_an_administrator_is_left_out_of_the_csv(self, tmp_path: Path):
        config = _config(tmp_path)
        _write_clean(
            config,
            [
                _professor(professor_name="Jane Doe", title="Associate Professor of Biology"),
                _professor(
                    professor_name="Rich Admin",
                    title="Senior Vice President of Advancement",
                    profile_url="https://www.acme.edu/people/rich-admin",
                ),
            ],
        )

        export.run(config, _checkpoint(config), logger)

        rows = list(csv.DictReader((Path(config.output_dir) / "master.csv").open()))
        assert [r["professor_name"] for r in rows] == ["Jane Doe"]

    def test_the_excluded_count_is_reported(self, tmp_path: Path):
        config = _config(tmp_path)
        _write_clean(
            config,
            [
                _professor(professor_name="Jane Doe", title="Professor of Biology"),
                _professor(
                    professor_name="Rich Admin",
                    title="Vice President of Student Affairs",
                    profile_url="https://www.acme.edu/people/rich-admin",
                ),
            ],
        )

        summary = export.run(config, _checkpoint(config), logger)

        assert any("1 row(s) excluded as non-faculty" in note for note in summary.notes)

    def test_an_unclassifiable_title_is_kept(self, tmp_path: Path):
        """Only a clear administrative title is grounds for exclusion; an
        unrecognised one is kept and labelled, never guessed away."""
        config = _config(tmp_path)
        _write_clean(config, [_professor(professor_name="Pat Curator", title="Curator")])

        export.run(config, _checkpoint(config), logger)

        rows = list(csv.DictReader((Path(config.output_dir) / "master.csv").open()))
        assert [r["professor_name"] for r in rows] == ["Pat Curator"]
        assert rows[0]["is_faculty"] == ""

    def test_the_csv_records_the_judgment(self, tmp_path: Path):
        config = _config(tmp_path)
        _write_clean(config, [_professor(title="Professor of Biology")])

        export.run(config, _checkpoint(config), logger)

        rows = list(csv.DictReader((Path(config.output_dir) / "master.csv").open()))
        assert rows[0]["is_faculty"] == "true"

    def test_coverage_counts_the_excluded_rows_per_school(self, tmp_path: Path):
        config = _config(tmp_path)
        _write_clean(
            config,
            [
                _professor(professor_name="Jane Doe", title="Professor of Biology"),
                _professor(
                    professor_name="Rich Admin",
                    title="Chief Financial Officer",
                    profile_url="https://www.acme.edu/people/rich-admin",
                ),
            ],
        )

        export.run(config, _checkpoint(config), logger)

        coverage = list(csv.DictReader((Path(config.output_dir) / "coverage.csv").open()))
        assert coverage[0]["professors_excluded_as_non_faculty"] == "1"

    def test_a_school_of_nothing_but_administrators_writes_no_csv(self, tmp_path: Path):
        config = _config(tmp_path)
        _write_clean(config, [_professor(professor_name="Rich Admin", title="Registrar")])

        export.run(config, _checkpoint(config), logger)

        assert not (Path(config.output_dir) / "by_school" / "acme-college.csv").exists()


class TestStaleSourceEntries:
    """A sitemap that still lists profiles the site has deleted is normal —
    15% of Agnes Scott's listed profiles 404. The crawler already handles it
    (a non-200 is recorded and never becomes a row); what was missing was
    saying so, so a school whose directory is a third dead reads the same as
    one that is current."""

    def _write_raw(self, config: Config, rows: list[tuple[str, str, int]]) -> None:
        path = Path(config.data_dir) / "profiles_raw.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                json.dumps(
                    {
                        "school_id": school_id,
                        "profile_url": url,
                        "directory_url": "https://www.acme.edu/faculty",
                        "http_status": status,
                        "html_cache_path": "/dev/null",
                        "fetched_at": "2026-08-04T18:22:10+00:00",
                        "parse_hint": {},
                    }
                )
                for school_id, url, status in rows
            )
            + "\n",
            encoding="utf-8",
        )

    def test_coverage_reports_dead_source_urls(self, tmp_path: Path):
        config = _config(tmp_path)
        _write_clean(config, [_professor(title="Professor of Biology")])
        self._write_raw(
            config,
            [
                ("acme-college", "https://www.acme.edu/faculty/jane-doe", 200),
                ("acme-college", "https://www.acme.edu/faculty/gone", 404),
                ("acme-college", "https://www.acme.edu/faculty/also-gone", 404),
            ],
        )

        export.run(config, _checkpoint(config), logger)

        coverage = list(csv.DictReader((Path(config.output_dir) / "coverage.csv").open()))
        assert coverage[0]["source_urls_dead"] == "2"
        assert coverage[0]["source_urls_fetched"] == "3"

    def test_a_current_directory_reports_zero(self, tmp_path: Path):
        config = _config(tmp_path)
        _write_clean(config, [_professor(title="Professor of Biology")])
        self._write_raw(
            config, [("acme-college", "https://www.acme.edu/faculty/jane-doe", 200)]
        )

        export.run(config, _checkpoint(config), logger)

        coverage = list(csv.DictReader((Path(config.output_dir) / "coverage.csv").open()))
        assert coverage[0]["source_urls_dead"] == "0"

    def test_unknown_when_the_raw_file_is_missing(self, tmp_path: Path):
        """Same rule as capped_at_limit: never report "0 dead" from an
        absence of evidence."""
        config = _config(tmp_path)
        _write_clean(config, [_professor(title="Professor of Biology")])

        export.run(config, _checkpoint(config), logger)

        coverage = list(csv.DictReader((Path(config.output_dir) / "coverage.csv").open()))
        assert coverage[0]["source_urls_dead"] == "unknown"

    def test_a_heavily_stale_directory_is_called_out_in_the_summary(self, tmp_path: Path):
        config = _config(tmp_path)
        _write_clean(config, [_professor(title="Professor of Biology")])
        self._write_raw(
            config,
            [("acme-college", f"https://www.acme.edu/faculty/p{i}", 200 if i < 8 else 404)
             for i in range(20)],
        )

        summary = export.run(config, _checkpoint(config), logger)

        assert any("STALE" in note and "60%" in note for note in summary.notes)
