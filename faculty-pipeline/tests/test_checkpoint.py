from __future__ import annotations

import json
from pathlib import Path

from faculty_pipeline.services.checkpoint import CheckpointStore


def test_is_done_false_for_unknown_key(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "discover.json")

    assert store.is_done("mit") is False


def test_completed_key_is_skipped(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "discover.json")

    store.mark_done("mit", meta={"directory_urls": ["https://mit.edu/faculty"]})

    assert store.is_done("mit") is True


def test_failed_key_is_retried(tmp_path: Path) -> None:
    """A crash costs one item, not the run: a failed key must NOT be
    considered done, so the next run's `is_done` check lets it be retried."""
    store = CheckpointStore(tmp_path / "crawl.json")

    store.mark_failed("https://example.edu/faculty/1", error="timeout")

    assert store.is_done("https://example.edu/faculty/1") is False
    entry = store.entry("https://example.edu/faculty/1")
    assert entry is not None
    assert entry.status == "failed"
    assert entry.last_error == "timeout"
    assert entry.attempts == 1


def test_retry_then_success_increments_attempts_and_clears_error(tmp_path: Path) -> None:
    path = tmp_path / "crawl.json"
    store = CheckpointStore(path)
    key = "https://example.edu/faculty/1"

    store.mark_failed(key, error="timeout")
    store.mark_done(key, meta={"http_status": 200})

    entry = store.entry(key)
    assert entry is not None
    assert entry.status == "done"
    assert entry.attempts == 2
    assert entry.last_error is None


def test_state_persists_across_store_instances(tmp_path: Path) -> None:
    path = tmp_path / "extract.json"
    CheckpointStore(path).mark_done("https://example.edu/p/1")

    reloaded = CheckpointStore(path)

    assert reloaded.is_done("https://example.edu/p/1") is True


def test_persisted_file_matches_spec_shape(tmp_path: Path) -> None:
    path = tmp_path / "discover.json"
    store = CheckpointStore(path)

    store.mark_done("mit", meta={"foo": "bar"})

    on_disk = json.loads(path.read_text())
    entry = on_disk["mit"]
    assert set(entry) == {"status", "attempts", "last_error", "updated_at", "meta"}
    assert entry["status"] == "done"


def test_corrupt_checkpoint_file_does_not_crash(tmp_path: Path) -> None:
    path = tmp_path / "discover.json"
    path.write_text("{not valid json")

    store = CheckpointStore(path)

    assert store.is_done("mit") is False


def test_summary_counts_by_status(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path / "crawl.json")
    store.mark_done("a")
    store.mark_done("b")
    store.mark_failed("c", error="boom")

    assert store.summary() == {"done": 2, "failed": 1}
