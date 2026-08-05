from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from faculty_pipeline.config import Config
from faculty_pipeline.services.checkpoint import CheckpointStore
from faculty_pipeline.stages import load_filter

FIXTURES = Path(__file__).parent / "fixtures"


def _config(tmp_path: Path, **overrides: object) -> Config:
    base = Config(
        input_path=FIXTURES / "catalog.sample.json",
        details_path=FIXTURES / "details.sample.json",
        data_dir=tmp_path / "data",
        checkpoint_dir=tmp_path / "checkpoints",
        log_dir=tmp_path / "logs",
    )
    return base.with_overrides(**overrides) if overrides else base


def _run(config: Config, *, dry_run: bool = False):
    checkpoint = CheckpointStore(Path(config.checkpoint_dir) / "load_filter.json")
    logger = logging.getLogger("faculty_pipeline.test_load_filter")
    return load_filter.run(config, checkpoint, logger, dry_run=dry_run)


def _read_output(config: Config) -> list[dict]:
    path = Path(config.data_dir) / "schools.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def test_keeps_only_us_schools(tmp_path: Path) -> None:
    config = _config(tmp_path)

    _run(config)

    rows = _read_output(config)
    ids = {row["school_id"] for row in rows}
    assert "acme-abroad-university" not in ids  # explicit non-US country
    assert "acme-ambiguous-college" not in ids  # no US signal at all
    assert "acme-state-university" in ids


def test_state_fallback_keeps_school_with_no_country_field(tmp_path: Path) -> None:
    config = _config(tmp_path)

    _run(config)

    rows = {row["school_id"]: row for row in _read_output(config)}
    assert "acme-noncountry-state-college" in rows
    assert rows["acme-noncountry-state-college"]["state"] == "NV"


def test_edu_fallback_keeps_school_with_no_country_or_state(tmp_path: Path) -> None:
    config = _config(tmp_path)

    _run(config)

    rows = {row["school_id"]: row for row in _read_output(config)}
    assert "acme-noncountry-edu-college" in rows


def test_low_confidence_keeps_are_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    config = _config(tmp_path)

    with caplog.at_level(logging.WARNING, logger="faculty_pipeline.test_load_filter"):
        summary = _run(config)

    assert any("low-confidence" in message for message in caplog.messages)
    assert any("low-confidence" in note for note in summary.notes)


def test_state_parsed_from_city_state_location(tmp_path: Path) -> None:
    config = _config(tmp_path)

    _run(config)

    rows = {row["school_id"]: row for row in _read_output(config)}
    assert rows["acme-state-university"]["state"] == "IL"
    assert rows["acme-tech"]["state"] == "MA"


def test_location_not_matching_city_state_shape_leaves_state_blank(tmp_path: Path) -> None:
    config = _config(tmp_path)

    _run(config)

    rows = {row["school_id"]: row for row in _read_output(config)}
    # Explicitly US (country field), but "Washington D.C." has no comma so
    # the "City, ST" parse can't extract a state — must not crash, must not
    # guess; state is left blank.
    assert "acme-odd-location-college" in rows
    assert rows["acme-odd-location-college"]["state"] is None


def test_homepage_normalized_to_https(tmp_path: Path) -> None:
    config = _config(tmp_path)

    _run(config)

    rows = {row["school_id"]: row for row in _read_output(config)}
    assert rows["acme-state-university"]["homepage"] == "https://www.acmestate.edu/"
    # Already-schemed homepages are left alone, not double-prefixed.
    assert rows["acme-tech"]["homepage"] == "https://web.acmetech.edu/"


def test_missing_homepage_drops_school_and_is_noted(tmp_path: Path) -> None:
    config = _config(tmp_path)

    summary = _run(config)

    rows = {row["school_id"]: row for row in _read_output(config)}
    assert "acme-no-homepage-university" not in rows
    assert any("missing homepage" in note for note in summary.notes)


def test_dedupes_by_slug_keeping_first_occurrence(tmp_path: Path) -> None:
    config = _config(tmp_path)

    summary = _run(config)

    rows = [row for row in _read_output(config) if row["school_id"] == "acme-tech"]
    assert len(rows) == 1
    # First occurrence in the fixture has the "web.acmetech.edu" homepage;
    # the later duplicate ("acmetech-duplicate.edu") must be dropped.
    assert rows[0]["homepage"] == "https://web.acmetech.edu/"
    assert any("duplicate" in note for note in summary.notes)


def test_details_passthrough_left_joined_by_school_id(tmp_path: Path) -> None:
    config = _config(tmp_path)

    _run(config)

    rows = {row["school_id"]: row for row in _read_output(config)}
    # Has a details entry: passthrough populated.
    assert rows["acme-tech"]["source_fields"]["faculty"]["count"] == 400
    # No details entry: still a valid school, with empty passthrough.
    assert rows["acme-state-university"]["source_fields"] == {}


def test_control_lowercased(tmp_path: Path) -> None:
    config = _config(tmp_path)

    _run(config)

    rows = {row["school_id"]: row for row in _read_output(config)}
    assert rows["acme-state-university"]["control"] == "public"
    assert rows["acme-tech"]["control"] == "private"


def test_missing_catalog_gives_actionable_error(tmp_path: Path) -> None:
    config = _config(tmp_path, input_path=tmp_path / "does-not-exist.json")

    with pytest.raises(load_filter.LoadFilterError, match="build_catalog.py"):
        _run(config)


def test_malformed_catalog_json_fails_fast(tmp_path: Path) -> None:
    bad_catalog = tmp_path / "bad.json"
    bad_catalog.write_text("{not valid json", encoding="utf-8")
    config = _config(tmp_path, input_path=bad_catalog)

    with pytest.raises(load_filter.LoadFilterError, match="malformed JSON"):
        _run(config)


def test_missing_details_file_is_non_fatal(tmp_path: Path) -> None:
    config = _config(tmp_path, details_path=tmp_path / "no-details-here.json")

    summary = _run(config)

    rows = _read_output(config)
    assert len(rows) == summary.processed
    assert all(row["source_fields"] == {} for row in rows)


def test_rerun_produces_byte_identical_output(tmp_path: Path) -> None:
    config = _config(tmp_path)
    output_path = Path(config.data_dir) / "schools.jsonl"

    _run(config)
    first = output_path.read_bytes()

    _run(config)
    second = output_path.read_bytes()

    assert first == second
    assert len(first) > 0


def test_output_sorted_deterministically_by_slug(tmp_path: Path) -> None:
    config = _config(tmp_path)

    _run(config)

    rows = _read_output(config)
    ids = [row["school_id"] for row in rows]
    assert ids == sorted(ids)


def test_dry_run_does_not_write_output(tmp_path: Path) -> None:
    config = _config(tmp_path)

    summary = _run(config, dry_run=True)

    assert not (Path(config.data_dir) / "schools.jsonl").exists()
    assert summary.processed > 0
