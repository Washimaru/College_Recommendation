"""Stage 2 — Discover Directories (§6 Stage 2).

For each school not already `done` in `checkpoints/discover.json`: try
heuristic URLs, query `services.search`, classify candidates via
`services.llm.classify_directory`, check `services.robots`, and append to
`data/directories.jsonl`. Not yet implemented (Milestone 3); this is a typed
stub so the CLI surface and stage signature are stable.
"""
from __future__ import annotations

import logging

from ..config import Config
from ..models import StageSummary
from ..services.checkpoint import CheckpointStore

STAGE_NAME = "discover"


def run(
    config: Config,
    checkpoint: CheckpointStore,
    logger: logging.Logger,
    *,
    limit: int | None = None,
    school_id: str | None = None,
) -> StageSummary:
    """Resumable per school_id: skips schools already `done` in the
    checkpoint unless `--force` is applied by the caller."""
    raise NotImplementedError(f"stages.{STAGE_NAME} lands in Milestone 3")
