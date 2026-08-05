"""A tiny JSON-backed progress store, one per stage (§5.6, §9).

This is what makes every stage resumable: `is_done(key)` lets a stage skip
work already finished on a prior run; `mark_failed(key, error)` records a
per-item failure without aborting the run, so a crash costs one item, not the
whole run — the next run retries only what's not `done`.

Keys are `school_id` (discover) or `profile_url` (crawl/extract). Each entry
is `{status, attempts, last_error, updated_at}` per §9.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

Status = Literal["done", "failed"]


@dataclass(frozen=True)
class CheckpointEntry:
    status: Status
    attempts: int
    last_error: str | None
    updated_at: str
    meta: dict[str, Any] = field(default_factory=dict)


class CheckpointStore:
    """JSON-backed per-stage checkpoint. One `CheckpointStore` per stage,
    persisted at `checkpoints/<stage>.json`."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, Any]] = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # A checkpoint file truncated by a mid-write crash shouldn't take
            # down the whole run; treat it as empty and let items be retried.
            return {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self._path)

    def is_done(self, key: str) -> bool:
        entry = self._data.get(key)
        return entry is not None and entry.get("status") == "done"

    def mark_done(self, key: str, meta: dict[str, Any] | None = None) -> None:
        with self._lock:
            self._data[key] = self._entry(key, status="done", error=None, meta=meta)
            self._save()

    def mark_failed(self, key: str, error: str) -> None:
        with self._lock:
            self._data[key] = self._entry(key, status="failed", error=error, meta=None)
            self._save()

    def entry(self, key: str) -> CheckpointEntry | None:
        raw = self._data.get(key)
        if raw is None:
            return None
        return CheckpointEntry(
            status=raw["status"],
            attempts=raw["attempts"],
            last_error=raw.get("last_error"),
            updated_at=raw["updated_at"],
            meta=raw.get("meta", {}),
        )

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for raw in self._data.values():
            counts[raw["status"]] = counts.get(raw["status"], 0) + 1
        return counts

    def _entry(
        self, key: str, *, status: Status, error: str | None, meta: dict[str, Any] | None
    ) -> dict[str, Any]:
        prev = self._data.get(key, {})
        return {
            "status": status,
            "attempts": prev.get("attempts", 0) + 1,
            "last_error": error,
            "updated_at": datetime.now(UTC).isoformat(),
            "meta": meta if meta is not None else prev.get("meta", {}),
        }
