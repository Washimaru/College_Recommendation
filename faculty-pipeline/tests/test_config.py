from __future__ import annotations

from pathlib import Path

import pytest

from faculty_pipeline.config import DEFAULT_RATE_LIMIT_SECONDS, Config


def test_load_applies_yaml_defaults(tmp_path: Path) -> None:
    yaml_path = tmp_path / "pipeline.yaml"
    yaml_path.write_text(
        "input_path: schools.json\nmax_retries: 7\nrespect_robots: false\n"
    )

    config = Config.load(yaml_path, env={})

    assert config.input_path == Path("schools.json")
    assert config.max_retries == 7
    assert config.respect_robots is False
    # Untouched keys keep their dataclass defaults.
    assert config.rate_limit_per_host == DEFAULT_RATE_LIMIT_SECONDS


def test_rate_limit_default_is_not_raised(tmp_path: Path) -> None:
    yaml_path = tmp_path / "pipeline.yaml"
    yaml_path.write_text("input_path: schools.json\n")

    config = Config.load(yaml_path, env={})

    assert config.rate_limit_per_host == 2.0


def test_env_override_wins_over_yaml(tmp_path: Path) -> None:
    yaml_path = tmp_path / "pipeline.yaml"
    yaml_path.write_text("input_path: schools.json\nmax_retries: 3\n")

    config = Config.load(yaml_path, env={"FACULTY_PIPELINE_MAX_RETRIES": "9"})

    assert config.max_retries == 9


def test_missing_input_path_raises(tmp_path: Path) -> None:
    yaml_path = tmp_path / "pipeline.yaml"
    yaml_path.write_text("max_retries: 3\n")

    with pytest.raises(ValueError, match="input_path"):
        Config.load(yaml_path, env={})


def test_unknown_key_raises(tmp_path: Path) -> None:
    yaml_path = tmp_path / "pipeline.yaml"
    yaml_path.write_text("input_path: schools.json\nnot_a_real_key: 1\n")

    with pytest.raises(ValueError, match="unknown config key"):
        Config.load(yaml_path, env={})


def test_missing_yaml_file_falls_back_to_env(tmp_path: Path) -> None:
    missing_path = tmp_path / "does-not-exist.yaml"

    config = Config.load(
        missing_path, env={"FACULTY_PIPELINE_INPUT_PATH": "from-env.json"}
    )

    assert config.input_path == Path("from-env.json")


def test_with_overrides_returns_new_instance(tmp_path: Path) -> None:
    yaml_path = tmp_path / "pipeline.yaml"
    yaml_path.write_text("input_path: schools.json\n")
    config = Config.load(yaml_path, env={})

    overridden = config.with_overrides(input_path=Path("other.json"))

    assert overridden.input_path == Path("other.json")
    assert config.input_path == Path("schools.json")  # original untouched
