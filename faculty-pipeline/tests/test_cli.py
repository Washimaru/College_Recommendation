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


def test_unimplemented_stage_exits_nonzero_with_clear_message(tmp_path: Path) -> None:
    result = CliRunner().invoke(main, [*_config_args(tmp_path), "discover"])

    assert result.exit_code != 0
    assert "not implemented" in result.output
    assert "Milestone 3" in result.output


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


def test_status_with_no_checkpoints(tmp_path: Path) -> None:
    result = CliRunner().invoke(main, [*_config_args(tmp_path), "status"])

    assert result.exit_code == 0
    assert "no checkpoints yet" in result.output


def test_status_reports_checkpoint_summary(tmp_path: Path) -> None:
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()
    CheckpointStore(checkpoint_dir / "discover.json").mark_done("mit")

    result = CliRunner().invoke(main, [*_config_args(tmp_path), "status"])

    assert result.exit_code == 0
    assert "discover" in result.output
    assert "'done': 1" in result.output


def test_clean_requires_yes_flag(tmp_path: Path) -> None:
    result = CliRunner().invoke(main, [*_config_args(tmp_path), "clean"])

    assert result.exit_code != 0
    assert "--yes" in result.output


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
