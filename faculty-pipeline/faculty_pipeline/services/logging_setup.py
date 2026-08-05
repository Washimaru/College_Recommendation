"""Structured logging to `logs/run-<timestamp>.log` and the console (§8).

Every record carries `stage`, `school_id`, and `url` (defaulting to `"-"`
when a caller doesn't pass them via `extra=`), so a run's log lines can be
grepped/aggregated by any of those dimensions.
"""
from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

LOGGER_NAME = "faculty_pipeline"
_CONTEXT_FIELDS = ("stage", "school_id", "url")
_FORMAT = "%(asctime)s %(levelname)-8s [%(stage)s] %(school_id)s %(url)s %(message)s"


class _ContextFilter(logging.Filter):
    """Fills in stage/school_id/url with '-' when a plain `logger.info(...)`
    call doesn't supply them, so the formatter never raises KeyError."""

    def filter(self, record: logging.LogRecord) -> bool:
        for field in _CONTEXT_FIELDS:
            if not hasattr(record, field):
                setattr(record, field, "-")
        return True


def configure_logging(
    log_dir: str | Path, level: str = "INFO", run_ts: str | None = None
) -> logging.Logger:
    """Configure and return the `faculty_pipeline` root logger: one handler to
    `logs/run-<run_ts>.log`, one to stderr. Safe to call more than once (e.g.
    once per CLI invocation) — handlers are replaced, not stacked."""
    log_dir_path = Path(log_dir)
    log_dir_path.mkdir(parents=True, exist_ok=True)
    ts = run_ts or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    log_path = log_dir_path / f"run-{ts}.log"

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False
    logger.handlers = []

    formatter = logging.Formatter(_FORMAT)
    context_filter = _ContextFilter()

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.addFilter(context_filter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(context_filter)
    logger.addHandler(console_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Child logger for a module, e.g. `get_logger(__name__)`. Inherits
    handlers from the `faculty_pipeline` logger once `configure_logging` has
    run; before that, records are dropped by the standard library's default
    "no handlers" behavior (with a one-time warning to stderr)."""
    return logging.getLogger(f"{LOGGER_NAME}.{name}")
