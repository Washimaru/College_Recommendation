"""Anthropic LLM wrapper for directory classification and profile extraction
(§5.5).

Typed stub — Milestone 1 only wires the `LLM` protocol shape.
`classify_directory` (used by Stage 2) lands in Milestone 3;
`extract_professor` (used by Stage 4) lands in Milestone 5. Both will cache
responses under `cache/llm/` keyed by prompt hash and enforce a JSON schema
via structured/tool output.
"""
from __future__ import annotations

from typing import Protocol

from ..config import Config
from ..models import Professor, School


class DirectoryClassification(dict):
    """Raw, UNTRUSTED LLM output for `classify_directory`. Expected keys:
    `directory_urls`, `confidence`, `notes`. Callers must validate before use,
    same trust-boundary posture as recommendation-service's `Review`."""


class LLM(Protocol):
    def classify_directory(
        self, candidates: list[str], school: School
    ) -> DirectoryClassification: ...

    def extract_professor(self, text: str, url: str, school: School) -> Professor: ...


class AnthropicLLM:
    """Wraps the Anthropic Messages API (`config.llm_model`,
    `config.llm_max_tokens`). Reads `ANTHROPIC_API_KEY` from the environment
    when implemented; not yet implemented in this milestone."""

    def __init__(self, config: Config) -> None:
        self._config = config

    def classify_directory(self, candidates: list[str], school: School) -> DirectoryClassification:
        raise NotImplementedError("services.llm.classify_directory lands in Milestone 3")

    def extract_professor(self, text: str, url: str, school: School) -> Professor:
        raise NotImplementedError("services.llm.extract_professor lands in Milestone 5")
