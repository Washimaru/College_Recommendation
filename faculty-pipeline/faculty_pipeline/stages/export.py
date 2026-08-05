"""Stage 5 — Export CSV (§6 Stage 5).

Reads `data/profiles_clean.jsonl`, groups by `school_id`, filters to rows at
or above the configured confidence threshold, writes
`output/by_school/<slug>.csv` per school and a concatenated
`output/master.csv`, and prints a `StageSummary`. Not yet implemented
(Milestone 6); this is a typed stub so the CLI surface and stage signature
are stable.
"""
from __future__ import annotations

import logging

from ..config import Config
from ..models import StageSummary
from ..services.checkpoint import CheckpointStore

STAGE_NAME = "export"


def run(config: Config, checkpoint: CheckpointStore, logger: logging.Logger) -> StageSummary:
    """Not checkpointed per-item (no network calls) — reruns simply overwrite
    the CSVs deterministically, same as Stage 1."""
    raise NotImplementedError(f"stages.{STAGE_NAME} lands in Milestone 6")
