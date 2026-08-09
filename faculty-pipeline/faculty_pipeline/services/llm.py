"""Anthropic LLM wrapper for directory classification and profile extraction
(§5.5).

`classify_directory` (used by Stage 2) was implemented in Milestone 3;
`extract_professor` (used by Stage 4) lands in Milestone 5. Both share the
same shape: Anthropic Messages API, structured output via a forced tool call
(`config.llm_model`, bounded by `config.llm_max_tokens`), response cached by
prompt hash under `cache/llm/`.

`classify_directory`'s job is discrimination, and the prompt
(`prompts/classify_directory.txt`) does the heavy lifting: accept official
campus-wide or department-level faculty directories, reject third-party
aggregators and superficially similar non-directory pages (handbooks, HR
postings, governance pages, alumni/student directories). The LLM output is
UNTRUSTED — this module only does structural validation (types, confidence
clamped to [0, 1]); the domain-level trust boundary (never accept a URL the
model invented outside the candidate list) is enforced by the caller,
`stages/discover.py`, the same posture as recommendation-service's
`sanitize_review`.

`classify_directory` also takes an optional `excerpts` mapping (candidate URL
-> a plain-text excerpt of that page's already-cached HTML, produced by
`utils.extract_text_excerpt`). This is evidence, not another fetch: Stage 2
already retrieved the page while resolve-checking the candidate, and passing
its content in is what lets the model judge "does this page actually list
people" instead of pattern-matching the URL. A candidate missing from the
mapping (or mapping to an empty string) is judged from its URL alone rather
than crashing.

`extract_professor`'s job is normalization, not discrimination of *whether*
to trust a value — that trust boundary (never accept an email/phone the
model didn't ground in the actual page) is enforced by the caller,
`stages/extract.py`, which cross-checks every returned email/phone against
the cleaned page text and the deterministic hints before it is allowed into
a `Professor` row. This module's job is: run the deterministic-pass hints
through the model, get back an untrusted `ProfessorExtraction`, and — since
this is the one call in the pipeline where a malformed tool response is
common enough to plan for — schema-validate the response and give the model
exactly one repair attempt (§6 Stage 4) before giving up.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol

from ..config import Config
from ..models import School
from ..utils import sha256_hex

TOOL_NAME = "classify_directory"
EXTRACT_TOOL_NAME = "extract_professor"

# §6 Stage 4 failure modes: "LLM returns invalid JSON (schema-validate + one
# repair retry, then skip + log)". One repair attempt after the first try.
_MAX_REPAIR_ATTEMPTS = 1

EXTRACT_PROFESSOR_TOOL: dict[str, Any] = {
    "name": EXTRACT_TOOL_NAME,
    "description": (
        "Extract a structured professor/staff record from one already-fetched "
        "university web page, or state that the page is not an individual's "
        "profile (a directory index, a 404, a news article, a department "
        "landing page, etc.)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "is_profile": {
                "type": "boolean",
                "description": (
                    "True only if this page is one specific named person's profile. "
                    "False for directory/listing pages, 404s, news articles, "
                    "department landing pages, or anything else that isn't an "
                    "individual's profile."
                ),
            },
            "professor_name": {
                "type": ["string", "null"],
                "description": (
                    "The person's full name exactly as written on the page, with "
                    "no trailing site/department boilerplate (e.g. no ' | School "
                    "Name'). Null when is_profile is false or no name is present."
                ),
            },
            "title": {
                "type": ["string", "null"],
                "description": "Academic/job title stated on the page, e.g. "
                "'Associate Professor of Physics'. Null if not stated.",
            },
            "department": {
                "type": ["string", "null"],
                "description": "Department or program stated on the page. Null if not stated.",
            },
            "email": {
                "type": ["string", "null"],
                "description": (
                    "An email address ONLY if it literally appears on the page or "
                    "in the deterministic hints. Never construct one from the "
                    "person's name and a guessed domain. Null if none appears."
                ),
            },
            "phone": {
                "type": ["string", "null"],
                "description": (
                    "A phone number ONLY if it literally appears on the page or in "
                    "the deterministic hints. Never invent one. Null if none appears."
                ),
            },
            "research_interests": {
                "type": ["string", "null"],
                "description": (
                    "Semicolon-separated list of research/teaching interests taken "
                    "from the page's own wording. Null if the page states none."
                ),
            },
            "confidence": {
                "type": "number",
                "description": "Confidence 0.0-1.0. 0 when is_profile is false or no name found.",
            },
            "notes": {
                "type": "string",
                "description": (
                    "One short sentence citing the evidence for is_profile and for "
                    "any field left null despite a hint suggesting a value."
                ),
            },
        },
        "required": [
            "is_profile",
            "professor_name",
            "title",
            "department",
            "email",
            "phone",
            "research_interests",
            "confidence",
            "notes",
        ],
        "additionalProperties": False,
    },
}

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


class ExtractionFailed(LLMError):
    """`extract_professor` produced a schema-invalid tool response twice — the
    initial attempt and one repair retry (§6 Stage 4 failure modes: "LLM
    returns invalid JSON ... schema-validate + one repair retry, then skip +
    log"). A subclass of `LLMError` so a caller that only wants the coarse
    "did the LLM call fail" signal still catches it, but `stages/extract.py`
    catches this specifically first and treats it as a skip for this one
    profile (marked done, not retried), not a transient failure like a
    network error — the same content is likely to fail the same way again."""


class DirectoryClassification(dict):
    """Raw, UNTRUSTED LLM output for `classify_directory`. Expected keys:
    `directory_urls`, `confidence`, `notes`. Callers must validate before use,
    same trust-boundary posture as recommendation-service's `Review`."""


class ProfessorExtraction(dict):
    """Raw, UNTRUSTED LLM output for `extract_professor`. Expected keys:
    `is_profile`, `professor_name`, `title`, `department`, `email`, `phone`,
    `research_interests`, `confidence`, `notes`. Callers (`stages/extract.py`)
    must validate before use — in particular, cross-check `email`/`phone`
    against the actual page text before trusting them; this module only does
    structural validation (types, bounds, the is_profile/professor_name
    consistency the repair loop enforces)."""


class LLM(Protocol):
    def classify_directory(
        self,
        candidates: list[str],
        school: School,
        excerpts: Mapping[str, str] | None = None,
    ) -> DirectoryClassification: ...

    def extract_professor(
        self,
        text: str,
        url: str,
        school: School,
        hints: Mapping[str, str | None] | None = None,
    ) -> ProfessorExtraction: ...


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
        self,
        candidates: list[str],
        school: School,
        excerpts: Mapping[str, str] | None = None,
    ) -> DirectoryClassification:
        if not candidates:
            return DirectoryClassification(
                directory_urls=[], confidence=0.0, notes="no candidates provided"
            )

        prompt = self._render_prompt(candidates, school, excerpts)
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

    def extract_professor(
        self,
        text: str,
        url: str,
        school: School,
        hints: Mapping[str, str | None] | None = None,
    ) -> ProfessorExtraction:
        prompt = self._render_extract_prompt(text, url, school, hints)
        cache_key = sha256_hex(prompt)
        cached = self._read_extract_cache(cache_key)
        if cached is not None:
            return cached

        # Multi-turn so a repair retry can show the model its own malformed
        # tool call plus a specific correction, rather than just resending
        # the identical first message and hoping for a different roll (§6
        # Stage 4: "schema-validate, one repair retry, then skip + log").
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        last_error = "unknown error"

        for attempt in range(_MAX_REPAIR_ATTEMPTS + 1):
            try:
                response = self._client.messages.create(
                    model=self._config.llm_model,
                    max_tokens=self._config.llm_max_tokens,
                    thinking={"type": "disabled"},
                    tools=[EXTRACT_PROFESSOR_TOOL],
                    tool_choice={"type": "tool", "name": EXTRACT_TOOL_NAME},
                    messages=messages,
                )
            except LLMError:
                raise
            except Exception as exc:  # noqa: BLE001 - any transport/API error is a stage failure
                raise LLMError(f"extract_professor request failed: {exc}") from exc

            if getattr(response, "stop_reason", None) == "refusal":
                raise LLMError("extract_professor request was refused by the model")

            tool_block = _find_tool_use_block(response, EXTRACT_TOOL_NAME)
            if tool_block is None:
                last_error = "no tool_use block in the model's response"
            else:
                raw = dict(tool_block.input)
                problem = _schema_problem(raw)
                if problem is None:
                    result = _coerce_extraction(raw)
                    self._write_extract_cache(cache_key, result)
                    return result
                last_error = problem

            if attempt < _MAX_REPAIR_ATTEMPTS:
                messages.append({"role": "assistant", "content": response.content})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Your response was invalid: {last_error}. Call the "
                            f"`{EXTRACT_TOOL_NAME}` tool again with a complete, "
                            "schema-valid response."
                        ),
                    }
                )

        raise ExtractionFailed(
            f"extract_professor: invalid response after one repair retry: {last_error}"
        )

    # -- prompt rendering ---------------------------------------------------

    def _render_prompt(
        self,
        candidates: list[str],
        school: School,
        excerpts: Mapping[str, str] | None,
    ) -> str:
        template = (self._prompts_dir / "classify_directory.txt").read_text(encoding="utf-8")
        excerpts = excerpts or {}
        candidate_list = "\n\n".join(
            self._render_candidate(url, excerpts.get(url)) for url in candidates
        )
        return template.format(
            school_name=school.name,
            homepage=school.homepage,
            candidate_list=candidate_list,
        )

    @staticmethod
    def _render_candidate(url: str, excerpt: str | None) -> str:
        excerpt = excerpt.strip() if isinstance(excerpt, str) else ""
        if not excerpt:
            return f'URL: {url}\nPage excerpt: (not retrieved; judge from the URL alone)'
        return f'URL: {url}\nPage excerpt:\n"""\n{excerpt}\n"""'

    def _extract_tool_input(self, response: Any) -> dict[str, Any]:
        if getattr(response, "stop_reason", None) == "refusal":
            raise LLMError("classify_directory request was refused by the model")
        for block in getattr(response, "content", []):
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == (
                TOOL_NAME
            ):
                return dict(block.input)
        raise LLMError("classify_directory: no tool_use block in the model's response")

    def _render_extract_prompt(
        self,
        text: str,
        url: str,
        school: School,
        hints: Mapping[str, str | None] | None,
    ) -> str:
        template = (self._prompts_dir / "extract_professor.txt").read_text(encoding="utf-8")
        return template.format(
            school_name=school.name,
            homepage=school.homepage,
            url=url,
            hints_block=_format_hints(hints or {}),
            page_text=text.strip() or "(no visible text extracted from this page)",
        )

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

    def _read_extract_cache(self, cache_key: str) -> ProfessorExtraction | None:
        path = self._cache_path(cache_key)
        if not path.exists():
            return None
        try:
            return ProfessorExtraction(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            return None

    def _write_extract_cache(self, cache_key: str, result: ProfessorExtraction) -> None:
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


# -- extract_professor helpers ----------------------------------------------

_EXTRACT_REQUIRED_KEYS = (
    "is_profile",
    "professor_name",
    "title",
    "department",
    "email",
    "phone",
    "research_interests",
    "confidence",
    "notes",
)


def _find_tool_use_block(response: Any, tool_name: str) -> Any | None:
    for block in getattr(response, "content", []):
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == (
            tool_name
        ):
            return block
    return None


def _schema_problem(raw: dict[str, Any]) -> str | None:
    """The repairable "invalid JSON" gate (§6 Stage 4): real structural
    problems in the tool call's input, distinct from `_coerce_extraction`'s
    lenient value coercion. Returns a human-readable description of the
    first problem found, or `None` if the response is schema-valid enough to
    coerce and use."""
    missing = [key for key in _EXTRACT_REQUIRED_KEYS if key not in raw]
    if missing:
        return f"missing required field(s): {', '.join(missing)}"
    if not isinstance(raw["is_profile"], bool):
        return "'is_profile' must be a boolean"
    try:
        float(raw["confidence"])
    except (TypeError, ValueError):
        return "'confidence' must be a number"
    name = raw["professor_name"]
    if raw["is_profile"] and not (isinstance(name, str) and name.strip()):
        return "'is_profile' is true but 'professor_name' is missing or empty"
    return None


def _coerce_extraction(raw: dict[str, Any]) -> ProfessorExtraction:
    """Structural validation/coercion only — NOT the domain trust boundary.
    `stages/extract.py` is responsible for cross-checking `email`/`phone`
    against the actual page content before trusting them, and for the final
    `professor_name` boilerplate-stripping guard."""
    is_profile = bool(raw.get("is_profile", False))
    name = _clean_opt_str(raw.get("professor_name")) if is_profile else None

    if not is_profile or not name:
        return ProfessorExtraction(
            is_profile=False,
            professor_name=None,
            title=None,
            department=None,
            email=None,
            phone=None,
            research_interests=None,
            confidence=0.0,
            notes=_clean_opt_str(raw.get("notes")) or "",
        )

    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    return ProfessorExtraction(
        is_profile=True,
        professor_name=name,
        title=_clean_opt_str(raw.get("title")),
        department=_clean_opt_str(raw.get("department")),
        email=_clean_opt_str(raw.get("email")),
        phone=_clean_opt_str(raw.get("phone")),
        research_interests=_clean_opt_str(raw.get("research_interests")),
        confidence=confidence,
        notes=_clean_opt_str(raw.get("notes")) or "",
    )


def _clean_opt_str(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _format_hints(hints: Mapping[str, str | None]) -> str:
    """Renders the deterministic-pass hints (`stages/extract.py`) as a short
    bullet list for the prompt. Only hints with an actual value are shown —
    an empty hints mapping renders as an explicit "none" line rather than a
    blank section, so the model isn't left guessing whether hints were
    omitted or genuinely absent."""
    lines = [f"- {key}: {value}" for key, value in hints.items() if value]
    if not lines:
        return "(no deterministic hints were found on this page)"
    return "\n".join(lines)


def _default_client() -> AnthropicClientLike:
    import anthropic

    return anthropic.Anthropic()
