from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from faculty_pipeline.cli import main
from faculty_pipeline.services.checkpoint import CheckpointStore

FIXTURES = Path(__file__).parent / "fixtures"


def _config_args(tmp_path: Path, input_path: str = "schools.json") -> list[str]:
    yaml_path = tmp_path / "pipeline.yaml"
    yaml_path.write_text(
        f"input_path: {input_path}\n"
        f"cache_dir: {tmp_path / 'cache'}\n"
        f"checkpoint_dir: {tmp_path / 'checkpoints'}\n"
        f"log_dir: {tmp_path / 'logs'}\n"
        f"data_dir: {tmp_path / 'data'}\n"
        f"output_dir: {tmp_path / 'output'}\n"
    )
    return ["--config", str(yaml_path)]


def test_help_lists_all_stage_commands() -> None:
    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0
    for command in ("load", "discover", "crawl", "extract", "export", "all", "status", "clean"):
        assert command in result.output


def test_export_missing_clean_profiles_gives_actionable_error_and_nonzero_exit(
    tmp_path: Path,
) -> None:
    # All six commands are implemented as of M6; `export` run before `extract`
    # has produced anything is the current representative of a fatal,
    # actionable per-stage error (mirrors test_load_missing_catalog_... above).
    result = CliRunner().invoke(main, [*_config_args(tmp_path), "export"])

    assert result.exit_code != 0
    assert "export failed" in result.output
    assert "profiles_clean.jsonl" in result.output


def test_load_missing_catalog_gives_actionable_error_and_nonzero_exit(tmp_path: Path) -> None:
    result = CliRunner().invoke(main, [*_config_args(tmp_path), "load"])

    assert result.exit_code != 0
    assert "build_catalog.py" in result.output


def test_load_writes_schools_jsonl(tmp_path: Path) -> None:
    args = _config_args(tmp_path, input_path=str(FIXTURES / "catalog.sample.json"))
    yaml_path = Path(args[1])
    yaml_path.write_text(
        yaml_path.read_text() + f"details_path: {FIXTURES / 'details.sample.json'}\n"
    )

    result = CliRunner().invoke(main, [*args, "load"])

    assert result.exit_code == 0, result.output
    assert "schools written" in result.output
    output_path = tmp_path / "data" / "schools.jsonl"
    assert output_path.exists()
    rows = [json.loads(line) for line in output_path.read_text().splitlines()]
    assert len(rows) > 0


def test_load_dry_run_does_not_write(tmp_path: Path) -> None:
    args = _config_args(tmp_path, input_path=str(FIXTURES / "catalog.sample.json"))
    yaml_path = Path(args[1])
    yaml_path.write_text(
        yaml_path.read_text() + f"details_path: {FIXTURES / 'details.sample.json'}\n"
    )

    result = CliRunner().invoke(main, ["--dry-run", *args, "load"])

    assert result.exit_code == 0, result.output
    assert not (tmp_path / "data" / "schools.jsonl").exists()


# -- `all` --------------------------------------------------------------


def test_dry_run_all_from_a_completely_empty_environment_plans_stage_1_and_stops(
    tmp_path: Path,
) -> None:
    """§11's smoke test, from scratch: `load --dry-run` never writes
    `data/schools.jsonl` (dry runs write nothing), so `discover` — the next
    stage in the chain — cannot find its input. `all --dry-run` must report
    that plainly and exit 0, not crash with a stack trace, since planning
    from an empty environment is exactly the case a smoke test exercises."""
    args = _config_args(tmp_path, input_path=str(FIXTURES / "catalog.sample.json"))

    result = CliRunner().invoke(main, ["--dry-run", *args, "all"])

    assert result.exit_code == 0, result.output
    assert "[dry-run] load:" in result.output
    assert "cannot plan yet" in result.output
    assert not (tmp_path / "data").exists() or not any((tmp_path / "data").iterdir())
    # Nothing was actually written or fetched.
    assert not (tmp_path / "output").exists()


def test_dry_run_all_plans_every_stage_when_upstream_artifacts_already_exist(
    tmp_path: Path,
) -> None:
    """With every stage's upstream artifact already on disk (the normal case
    for `--dry-run all` on a pipeline that's been run before), the full
    chain plans end-to-end with no network/LLM calls and no writes — and,
    per M6, without needing a real ANTHROPIC_API_KEY: dry_run short-circuits
    each stage before any LLM client is touched."""
    args = _config_args(tmp_path, input_path=str(FIXTURES / "catalog.sample.json"))
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "schools.jsonl").write_text(
        json.dumps(
            {
                "school_id": "acme-college",
                "name": "Acme College",
                "slug": "acme-college",
                "country": "US",
                "homepage": "https://www.acme.edu",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (data_dir / "directories.jsonl").write_text(
        json.dumps(
            {
                "school_id": "acme-college",
                "directory_urls": ["https://www.acme.edu/faculty"],
                "discovery_method": "heuristic",
                "robots_allowed": True,
                "confidence": 0.8,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (data_dir / "profiles_raw.jsonl").write_text(
        json.dumps(
            {
                "school_id": "acme-college",
                "profile_url": "https://www.acme.edu/faculty/jane-doe",
                "directory_url": "https://www.acme.edu/faculty",
                "html_cache_path": str(tmp_path / "jane-doe.html"),
                "fetched_at": "2026-08-04T18:22:10Z",
                "http_status": 200,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (data_dir / "profiles_clean.jsonl").write_text(
        json.dumps(
            {
                "school_id": "acme-college",
                "school_name": "Acme College",
                "professor_name": "Jane Doe",
                "profile_url": "https://www.acme.edu/faculty/jane-doe",
                "directory_url": "https://www.acme.edu/faculty",
                "extraction_confidence": 0.9,
                "extracted_at": "2026-08-04T18:22:10Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(main, ["--dry-run", *args, "all"])

    assert result.exit_code == 0, result.output
    for line in (
        "[dry-run] load:",
        "[dry-run] discover:",
        "[dry-run] crawl:",
        "[dry-run] extract:",
        "[dry-run] export:",
    ):
        assert line in result.output
    assert "cannot plan yet" not in result.output
    # No side effects anywhere.
    assert not (tmp_path / "output").exists()
    assert (data_dir / "schools.jsonl").read_text(encoding="utf-8").count("\n") == 1


def test_all_force_clears_checkpoints_and_warns_about_append_only_duplicates(
    tmp_path: Path,
) -> None:
    args = _config_args(tmp_path, input_path=str(FIXTURES / "catalog.sample.json"))
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir(parents=True)
    CheckpointStore(checkpoint_dir / "discover.json").mark_done("acme-college")

    result = CliRunner().invoke(main, ["--dry-run", *args, "all", "--force"])

    assert result.exit_code == 0, result.output
    assert "--force: cleared checkpoint(s)" in result.output
    assert "duplicate rows" in result.output
    assert not (checkpoint_dir / "discover.json").exists()


def test_status_with_nothing_run_yet(tmp_path: Path) -> None:
    result = CliRunner().invoke(main, [*_config_args(tmp_path), "status"])

    assert result.exit_code == 0
    for stage_line in (
        "load     : not run yet",
        "discover : not run yet",
        "crawl    : not run yet",
        "extract  : not run yet",
        "export   : not run yet",
    ):
        assert stage_line in result.output


def test_status_reports_checkpoint_done_failed_pending(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "schools.jsonl").write_text(
        '{"school_id": "mit"}\n{"school_id": "reed"}\n', encoding="utf-8"
    )
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()
    CheckpointStore(checkpoint_dir / "discover.json").mark_done("mit")

    result = CliRunner().invoke(main, [*_config_args(tmp_path), "status"])

    assert result.exit_code == 0
    assert "discover : done 1, failed 0, pending 1  (of 2 school(s)" in result.output


def test_status_reports_export_summary_and_coverage(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "master.csv").write_text(
        "school_id,school_name\nagnes-scott-college,Agnes Scott College\n", encoding="utf-8"
    )
    (output_dir / "coverage.csv").write_text(
        "school_id,incomplete\nagnes-scott-college,false\nbard-college,true\n", encoding="utf-8"
    )

    result = CliRunner().invoke(main, [*_config_args(tmp_path), "status"])

    assert result.exit_code == 0
    assert "export   : 1 professor(s) across 1 school(s) in output/master.csv" in result.output
    assert "1 of 2 school(s) with clean data incomplete" in result.output


def test_clean_requires_yes_flag(tmp_path: Path) -> None:
    result = CliRunner().invoke(main, [*_config_args(tmp_path), "clean"])

    assert result.exit_code != 0
    assert "--yes" in result.output
    # States exactly what it will delete before refusing, not just "pass --yes".
    assert str(tmp_path / "cache") in result.output
    assert str(tmp_path / "checkpoints") in result.output


def test_clean_does_not_delete_without_yes(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    (cache_dir / "html").mkdir()

    CliRunner().invoke(main, [*_config_args(tmp_path), "clean"])

    assert cache_dir.exists()


def test_clean_removes_cache_and_checkpoints(tmp_path: Path) -> None:
    cache_dir = tmp_path / "cache"
    checkpoint_dir = tmp_path / "checkpoints"
    cache_dir.mkdir()
    checkpoint_dir.mkdir()
    (cache_dir / "html").mkdir()

    result = CliRunner().invoke(main, [*_config_args(tmp_path), "clean", "--yes"])

    assert result.exit_code == 0
    assert not cache_dir.exists()
    assert not checkpoint_dir.exists()
