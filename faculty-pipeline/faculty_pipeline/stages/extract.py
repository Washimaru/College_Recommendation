"""Stage 4 — Extract & Normalize (§6 Stage 4).

For each `RawProfile` not already `done` in `checkpoints/extract.json`: a
deterministic pass (strip HTML, pull mailto/tel/meta/JSON-LD hints, de-obfuscate
emails), then an LLM pass via `services.llm.extract_professor` (skippable with
`no_llm=True` for debugging), then validation (require `professor_name`).
Appends to `data/profiles_clean.jsonl`. Not yet implemented (Milestone 5);
this is a typed stub so the CLI surface and stage signature are stable.
"""
from __future__ import annotations

import logging

from ..config import Config
from ..models import StageSummary
from ..services.checkpoint import CheckpointStore

STAGE_NAME = "extract"


def run(
    config: Config,
    checkpoint: CheckpointStore,
    logger: logging.Logger,
    *,
    school_id: str | None = None,
    no_llm: bool = False,
) -> StageSummary:
    """Resumable per profile_url. Cached by prompt hash under `cache/llm/`, so
    re-runs after a `--force` crawl are nearly free."""
    raise NotImplementedError(f"stages.{STAGE_NAME} lands in Milestone 5")
