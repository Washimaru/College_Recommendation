"""Frozen dataclass config, loaded from `config/pipeline.yaml` with
environment-variable overrides. Keys per docs/FACULTY_PIPELINE.md §5.1, plus
`checkpoint_dir`/`log_dir` (needed by services/checkpoint.py and
services/logging_setup.py; the §3 tree has `checkpoints/` and `logs/` dirs but
§5.1's key list omits them).

Secrets (`ANTHROPIC_API_KEY`, `SEARCH_API_KEY`) are deliberately NOT config
fields — they're read directly from the environment by services/llm.py and
services/search.py once those land, via `.env` (see .env.example).
"""
from __future__ import annotations

import dataclasses
import os
from collections.abc import Mapping
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

import yaml

# Prefix for environment-variable overrides, e.g. FACULTY_PIPELINE_MAX_RETRIES.
ENV_PREFIX = "FACULTY_PIPELINE_"

# §5.1: "rate_limit_per_host (default 1 req/2s)". Stored as the minimum number
# of seconds between requests to the same host, not requests/sec, so the
# default is a readable 2.0 rather than a fractional 0.5. http_client.py's
# rate limiter must never go below this.
DEFAULT_RATE_LIMIT_SECONDS = 2.0


@dataclass(frozen=True)
class Config:
    input_path: Path
    # Stage 1 (§6 Stage 1, adapted per the docs/FACULTY_PIPELINE.md banner):
    # `input_path` is the catalog (country/homepage). `details_path` is
    # `school_details.json`, left-joined by school id for the `source_fields`
    # passthrough (§4.1). Not every school has an entry there — that's the
    # common case, not an error.
    details_path: Path = Path("../data-pipeline/sources/school_details.json")
    output_dir: Path = Path("output")
    data_dir: Path = Path("data")
    cache_dir: Path = Path("cache")
    checkpoint_dir: Path = Path("checkpoints")
    log_dir: Path = Path("logs")

    rate_limit_per_host: float = DEFAULT_RATE_LIMIT_SECONDS
    max_concurrency: int = 4
    request_timeout: float = 15.0
    max_retries: int = 3

    user_agent: str = (
        "UniMatchFacultyBot/0.1 "
        "(+https://github.com/unimatch/faculty-pipeline; "
        "contact: faculty-pipeline@unimatch.example)"
    )

    # Current model id. `claude-sonnet-4-5` is a previous generation and may
    # not resolve; extraction is structured-output work where reliability
    # matters more than the token price, so Sonnet 5 is the default. For very
    # large runs, `claude-haiku-4-5-20251001` trades some accuracy for cost.
    llm_model: str = "claude-sonnet-5"
    llm_max_tokens: int = 1024

    # Stage 2 (discover.py): cap on the plain-text excerpt of a candidate
    # page's cached HTML that gets embedded in the classify_directory prompt
    # as evidence. Bounds token cost alongside llm_max_tokens; a few thousand
    # characters is enough to show whether a page lists people, departments,
    # or just a search box.
    directory_excerpt_max_chars: int = 4000

    # None => no provider configured; services/search.py degrades to
    # returning no candidates rather than raising (see its module docstring).
    search_provider: str | None = None

    # Deliberately conservative. 268 US schools x 500 profiles would be 134,000
    # fetches, and at the 2s/host floor that is days of crawling other people's
    # servers. Raise it per-run once a school's directory is known to be worth
    # it, rather than defaulting to the ceiling.
    max_profiles_per_school: int = 100
    respect_robots: bool = True

    @classmethod
    def load(
        cls,
        path: str | Path = "config/pipeline.yaml",
        env: Mapping[str, str] | None = None,
    ) -> Config:
        """Load defaults from `path` (if it exists), then apply
        `FACULTY_PIPELINE_<FIELD>` environment overrides (from `env`, default
        `os.environ`). Unknown YAML keys are rejected so a typo in the config
        file fails loudly instead of being silently ignored.
        """
        raw: dict[str, Any] = {}
        yaml_path = Path(path)
        if yaml_path.exists():
            loaded = yaml.safe_load(yaml_path.read_text()) or {}
            if not isinstance(loaded, dict):
                raise ValueError(f"{yaml_path}: expected a YAML mapping at the top level")
            raw = dict(loaded)

        known = {f.name for f in fields(cls)}
        unknown = set(raw) - known
        if unknown:
            raise ValueError(f"{yaml_path}: unknown config key(s): {sorted(unknown)}")

        environ = env if env is not None else os.environ
        for f in fields(cls):
            env_key = ENV_PREFIX + f.name.upper()
            if env_key in environ:
                raw[f.name] = environ[env_key]

        if "input_path" not in raw:
            raise ValueError(f"{yaml_path}: 'input_path' is required (no default)")

        coerced = {name: _coerce(name, value, cls) for name, value in raw.items()}
        return cls(**coerced)

    def with_overrides(self, **kwargs: Any) -> Config:
        """Return a copy with the given fields replaced (the dataclass is
        frozen, so this is the supported way to adjust it, e.g. for
        `--input`/`--dry-run` CLI overrides)."""
        return dataclasses.replace(self, **kwargs)


_PATH_FIELDS = {
    "input_path",
    "details_path",
    "output_dir",
    "data_dir",
    "cache_dir",
    "checkpoint_dir",
    "log_dir",
}
_FLOAT_FIELDS = {"rate_limit_per_host", "request_timeout"}
_INT_FIELDS = {
    "max_concurrency",
    "max_retries",
    "llm_max_tokens",
    "max_profiles_per_school",
    "directory_excerpt_max_chars",
}
_BOOL_FIELDS = {"respect_robots"}


def _coerce(name: str, value: Any, cls: type[Config]) -> Any:
    if value is None:
        return None
    if name in _PATH_FIELDS:
        return Path(value)
    if name in _FLOAT_FIELDS:
        return float(value)
    if name in _INT_FIELDS:
        return int(value)
    if name in _BOOL_FIELDS:
        return _as_bool(value) if isinstance(value, str) else bool(value)
    return value


def _as_bool(value: str) -> bool:
    if value.strip().lower() in ("1", "true", "yes", "on"):
        return True
    if value.strip().lower() in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"cannot parse {value!r} as a boolean")
