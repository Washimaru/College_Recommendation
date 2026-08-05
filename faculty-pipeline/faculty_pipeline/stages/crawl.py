"""Stage 3 — Crawl Profiles (§6 Stage 3).

For each directory URL: fetch via `services.http_client`, enumerate
same-domain profile links (with a pagination cap), then fetch each profile
URL not already `done` in `checkpoints/crawl.json`, cache the HTML, and
append a `models.RawProfile` row. Enforces `config.max_profiles_per_school`.
Not yet implemented (Milestone 4); this is a typed stub so the CLI surface
and stage signature are stable.
"""
from __future__ import annotations

import logging

from ..config import Config
from ..models import StageSummary
from ..services.checkpoint import CheckpointStore

STAGE_NAME = "crawl"


def run(
    config: Config,
    checkpoint: CheckpointStore,
    logger: logging.Logger,
    *,
    limit: int | None = None,
    school_id: str | None = None,
    dynamic: bool = False,
) -> StageSummary:
    """Resumable per profile_url. `dynamic=True` enables the headless-browser
    fallback for JS-rendered directories (opt-in, off by default per §13)."""
    raise NotImplementedError(f"stages.{STAGE_NAME} lands in Milestone 4")
