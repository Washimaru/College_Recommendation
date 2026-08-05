"""Pluggable web-search adapter for directory discovery (§5.4).

Typed stub — Milestone 1 only wires the shape; real providers (Brave, Bing,
SerpAPI) land in Milestone 3.

**No `SEARCH_API_KEY` is configured for this project** (see the adaptation
banner at the top of docs/FACULTY_PIPELINE.md). `build_search_provider`
therefore falls back to `NullSearchProvider` whenever `config.search_provider`
is unset, so `discover.py` can run heuristics-only (§6 Stage 2) without ever
raising for a missing key. Do not make this factory raise on a missing
provider — a degraded discovery pass is the intended behavior, not an error.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..config import Config


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str
    snippet: str = ""


class SearchProvider(Protocol):
    def search(self, query: str) -> list[SearchResult]: ...


class NullSearchProvider:
    """No-op provider: always returns zero candidates. This is the default
    when no search provider/API key is configured."""

    def search(self, query: str) -> list[SearchResult]:
        return []


def build_search_provider(config: Config) -> SearchProvider:
    """Factory selecting a provider by `config.search_provider`. Callers
    (discover.py) never need to special-case a missing key: this always
    returns *something* that implements `SearchProvider`."""
    if not config.search_provider:
        return NullSearchProvider()
    # Real provider hookups (Brave/Bing/SerpAPI) land in Milestone 3.
    raise NotImplementedError(
        f"search provider {config.search_provider!r} is not implemented yet "
        "(lands in Milestone 3); leave search_provider unset to use "
        "NullSearchProvider"
    )
