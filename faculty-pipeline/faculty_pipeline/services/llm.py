"""Anthropic LLM wrapper for directory classification and profile extraction
(§5.5).

`classify_directory` (used by Stage 2) is implemented here, per Milestone 3:
Anthropic Messages API, structured output via a forced tool call
(`config.llm_model`, bounded by `config.llm_max_tokens`), response cached by
prompt hash under `cache/llm/`. `extract_professor` (used by Stage 4) lands
in Milestone 5.

Its job is discrimination, and the prompt (`prompts/classify_directory.txt`)
does the heavy lifting: accept official campus-wide or department-level
faculty directories, reject third-party aggregators and superficially
similar non-directory pages (handbooks, HR postings, governance pages,
alumni/student directories). The LLM output is UNTRUSTED — this module only
does structural validation (types, confidence clamped to [0, 1]); the
domain-level trust boundary (never accept a URL the model invented outside
the candidate list) is enforced by the caller, `stages/discover.py`, the
same posture as recommendation-service's `sanitize_review`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from ..config import Config
from ..models import Professor, School
from ..utils import sha256_hex

TOOL_NAME = "classify_directory"

CLASSIFY_DIRECTORY_TOOL: dict[str, Any] = {
    "name": TOOL_NAME,
    "description": (
        "Classify and rank candidate URLs as official, on-domain faculty/people "
        "directories for a US university. Reject third-party aggregators and "
        "non-directory pages (handbooks, HR postings, governance pages, alumni "
        "or student directories)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "directory_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Official, on-domain faculty/people directory URLs from the "
                    "candidate list, ranked best first. Empty if none qualify."
                ),
            },
            "confidence": {
                "type": "number",
                "description": (
                    "Confidence 0.0-1.0 that directory_urls are correct official "
                    "directories. 0 when directory_urls is empty."
                ),
            },
            "notes": {
                "type": "string",
                "description": (
                    "Brief rationale: why candidates were accepted/rejected, or "
                    "why multiple department pages were kept. Empty string if "
                    "there is nothing to note."
                ),
            },
        },
        "required": ["directory_urls", "confidence", "notes"],
        "additionalProperties": False,
    },
}


class LLMError(RuntimeError):
    """A search/LLM call failed. Caught by stages/discover.py, which marks
    the school `failed` (retried next run) rather than aborting the run."""


class DirectoryClassification(dict):
    """Raw, UNTRUSTED LLM output for `classify_directory`. Expected keys:
    `directory_urls`, `confidence`, `notes`. Callers must validate before use,
    same trust-boundary posture as recommendation-service's `Review`."""


class LLM(Protocol):
    def classify_directory(
        self, candidates: list[str], school: School
    ) -> DirectoryClassification: ...

    def extract_professor(self, text: str, url: str, school: School) -> Professor: ...


class _AnthropicMessages(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


class AnthropicClientLike(Protocol):
    """The subset of `anthropic.Anthropic` this module needs. A Protocol so
    tests can inject a fake client without real API calls."""

    messages: _AnthropicMessages


class AnthropicLLM:
    """Wraps the Anthropic Messages API (`config.llm_model`,
    `config.llm_max_tokens`). Reads `ANTHROPIC_API_KEY` from the environment
    via the default `anthropic.Anthropic()` client construction when no
    client is injected."""

    def __init__(
        self,
        config: Config,
        client: AnthropicClientLike | None = None,
        prompts_dir: str | Path = "prompts",
    ) -> None:
        self._config = config
        self._client = client if client is not None else _default_client()
        self._prompts_dir = Path(prompts_dir)
        self._cache_dir = Path(config.cache_dir) / "llm"

    def classify_directory(
        self, candidates: list[str], school: School
    ) -> DirectoryClassification:
        if not candidates:
            return DirectoryClassification(
                directory_urls=[], confidence=0.0, notes="no candidates provided"
            )

        prompt = self._render_prompt(candidates, school)
        cache_key = sha256_hex(prompt)
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached

        try:
            response = self._client.messages.create(
                model=self._config.llm_model,
                max_tokens=self._config.llm_max_tokens,
                thinking={"type": "disabled"},
                tools=[CLASSIFY_DIRECTORY_TOOL],
                tool_choice={"type": "tool", "name": TOOL_NAME},
                messages=[{"role": "user", "content": prompt}],
            )
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001 - any transport/API error is a stage failure
            raise LLMError(f"classify_directory request failed: {exc}") from exc

        raw = self._extract_tool_input(response)
        result = _coerce_classification(raw)
        self._write_cache(cache_key, result)
        return result

    def extract_professor(self, text: str, url: str, school: School) -> Professor:
        raise NotImplementedError("services.llm.extract_professor lands in Milestone 5")

    # -- prompt rendering ---------------------------------------------------

    def _render_prompt(self, candidates: list[str], school: School) -> str:
        template = (self._prompts_dir / "classify_directory.txt").read_text(encoding="utf-8")
        candidate_list = "\n".join(f"- {url}" for url in candidates)
        return template.format(
            school_name=school.name,
            homepage=school.homepage,
            candidate_list=candidate_list,
        )

    def _extract_tool_input(self, response: Any) -> dict[str, Any]:
        if getattr(response, "stop_reason", None) == "refusal":
            raise LLMError("classify_directory request was refused by the model")
        for block in getattr(response, "content", []):
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == (
                TOOL_NAME
            ):
                return dict(block.input)
        raise LLMError("classify_directory: no tool_use block in the model's response")

    # -- cache (§5.5: cache LLM responses by prompt hash under cache/llm/) --

    def _cache_path(self, cache_key: str) -> Path:
        return self._cache_dir / f"{cache_key}.json"

    def _read_cache(self, cache_key: str) -> DirectoryClassification | None:
        path = self._cache_path(cache_key)
        if not path.exists():
            return None
        try:
            return DirectoryClassification(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            return None

    def _write_cache(self, cache_key: str, result: DirectoryClassification) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_path(cache_key).write_text(
            json.dumps(dict(result), indent=2), encoding="utf-8"
        )


def _coerce_classification(raw: dict[str, Any]) -> DirectoryClassification:
    """Structural validation only (types, bounds) — NOT the domain trust
    boundary. `stages/discover.py` is responsible for rejecting any URL the
    model returned that wasn't in the candidate list it was given."""
    urls_raw = raw.get("directory_urls", [])
    directory_urls: list[str] = []
    if isinstance(urls_raw, list):
        seen: set[str] = set()
        for item in urls_raw:
            if isinstance(item, str) and item and item not in seen:
                directory_urls.append(item)
                seen.add(item)

    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    if not directory_urls:
        confidence = 0.0

    notes = raw.get("notes")
    notes = notes.strip() if isinstance(notes, str) and notes.strip() else None

    return DirectoryClassification(
        directory_urls=directory_urls, confidence=confidence, notes=notes
    )


def _default_client() -> AnthropicClientLike:
    import anthropic

    return anthropic.Anthropic()
