"""An empty catalog is a failed load, not a valid answer.

`docker compose up -d` passes its healthcheck before `data-pipeline/load.py`
runs, so a query against the unseeded `universities` table returns `[]` — no
exception. Caching that empty list serves zero schools, silently, until the
process restarts. The empty result must fall back to the seed, say so in the
log, and stay uncached so the next request sees the loaded table.
"""
from __future__ import annotations

import logging

import pytest

from app import candidates


@pytest.fixture(autouse=True)
def _clear_cache():
    candidates.reset_cache()
    yield
    candidates.reset_cache()


def test_an_empty_db_result_falls_back_to_the_seed(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://unseeded/db")
    monkeypatch.setattr(candidates, "_load_from_db", lambda url: [])

    assert len(candidates.load_universities()) > 0


def test_an_empty_db_result_is_not_cached(monkeypatch):
    """The unseeded window is transient; the next request must retry the DB."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://unseeded/db")
    loaded = candidates._load_from_seed()[:1]
    calls: list[str] = []

    def db_fills_up(url: str) -> list:
        calls.append(url)
        return [] if len(calls) == 1 else loaded

    monkeypatch.setattr(candidates, "_load_from_db", db_fills_up)

    first = candidates.load_universities()
    second = candidates.load_universities()

    assert len(calls) == 2, "the empty result was cached instead of retried"
    assert len(first) > len(loaded), "an empty catalog was served instead of the seed"
    assert second == loaded


def test_a_failed_db_load_is_not_cached_either(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://down/db")
    loaded = candidates._load_from_seed()[:1]
    calls: list[str] = []

    def db_recovers(url: str) -> list:
        calls.append(url)
        if len(calls) == 1:
            raise RuntimeError("connection refused")
        return loaded

    monkeypatch.setattr(candidates, "_load_from_db", db_recovers)

    candidates.load_universities()

    assert candidates.load_universities() == loaded


def test_an_empty_db_result_is_logged(monkeypatch, caplog):
    monkeypatch.setenv("DATABASE_URL", "postgresql://unseeded/db")
    monkeypatch.setattr(candidates, "_load_from_db", lambda url: [])

    with caplog.at_level(logging.WARNING, logger=candidates.__name__):
        candidates.load_universities()

    assert caplog.records, "an empty catalog was served with no log line"
    assert "seed" in caplog.text.lower()


def test_a_loaded_catalog_is_still_cached(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://seeded/db")
    loaded = candidates._load_from_seed()
    calls: list[str] = []

    def db(url: str) -> list:
        calls.append(url)
        return loaded

    monkeypatch.setattr(candidates, "_load_from_db", db)

    candidates.load_universities()
    candidates.load_universities()

    assert len(calls) == 1


def test_the_seed_is_cached_when_there_is_no_database(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    calls: list[int] = []
    real_seed = candidates._load_from_seed

    def counted_seed() -> list:
        calls.append(1)
        return real_seed()

    monkeypatch.setattr(candidates, "_load_from_seed", counted_seed)

    candidates.load_universities()
    candidates.load_universities()

    assert len(calls) == 1
