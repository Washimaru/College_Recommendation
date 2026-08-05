"""Stage 1 — Load & Filter (§6 Stage 1).

Reads `school_details.json`, keeps U.S. schools only, normalizes into
`models.School`, writes `data/schools.jsonl`. Not yet implemented (Milestone
2); this is a typed stub so the CLI surface and stage signature are stable.
"""
from __future__ import annotations

import logging

from ..config import Config
from ..models import StageSummary
from ..services.checkpoint import CheckpointStore

STAGE_NAME = "load_filter"


def run(config: Config, checkpoint: CheckpointStore, logger: logging.Logger) -> StageSummary:
    """Load `config.input_path`, filter to U.S. schools, write
    `data/schools.jsonl`. Idempotent: overwrites the output deterministically
    rather than checkpointing per-item (there's no per-school network call in
    this stage)."""
    raise NotImplementedError(f"stages.{STAGE_NAME} lands in Milestone 2")
