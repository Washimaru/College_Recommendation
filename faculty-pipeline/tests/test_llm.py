from __future__ import annotations

from pathlib import Path

import pytest

from faculty_pipeline.config import Config
from faculty_pipeline.models import School
from faculty_pipeline.services.llm import TOOL_NAME, AnthropicLLM, LLMError


def _school(**overrides: object) -> School:
    defaults: dict[str, object] = dict(
        school_id="acme-tech",
        name="Acme Tech",
        slug="acme-tech",
        country="US",
        homepage="https://www.acmetech.edu/",
    )
    defaults.update(overrides)
    return School(**defaults)  # type: ignore[arg-type]


def _config(tmp_path: Path) -> Config:
    return Config(input_path=tmp_path / "schools.json", cache_dir=tmp_path / "cache")


def _prompts_dir(tmp_path: Path) -> Path:
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "classify_directory.txt").write_text(
        "school={school_name} home={homepage}\n{candidate_list}\n", encoding="utf-8"
    )
    return prompts


class FakeToolUseBlock:
    type = "tool_use"

    def __init__(self, name: str, input: dict) -> None:  # noqa: A002 - matches SDK field name
        self.name = name
        self.input = input


class FakeTextBlock:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class FakeResponse:
    def __init__(self, content: list, stop_reason: str = "tool_use") -> None:
        self.content = content
        self.stop_reason = stop_reason


class FakeMessages:
    def __init__(self, response: FakeResponse | None = None, exc: Exception | None = None) -> None:
        self._response = response
        self._exc = exc
        self.calls: list[dict] = []

    def create(self, **kwargs: object) -> FakeResponse:
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        assert self._response is not None
        return self._response


class FakeClient:
    def __init__(self, response: FakeResponse | None = None, exc: Exception | None = None) -> None:
        self.messages = FakeMessages(response, exc)


def _llm(tmp_path: Path, client: FakeClient) -> AnthropicLLM:
    return AnthropicLLM(_config(tmp_path), client=client, prompts_dir=_prompts_dir(tmp_path))


def test_no_candidates_returns_empty_without_calling_client(tmp_path: Path) -> None:
    client = FakeClient()
    llm = _llm(tmp_path, client)

    result = llm.classify_directory([], _school())

    assert result == {"directory_urls": [], "confidence": 0.0, "notes": "no candidates provided"}
    assert client.messages.calls == []


def test_classify_directory_returns_structured_result(tmp_path: Path) -> None:
    response = FakeResponse(
        [
            FakeToolUseBlock(
                TOOL_NAME,
                {
                    "directory_urls": ["https://acmetech.edu/faculty"],
                    "confidence": 0.9,
                    "notes": "campus-wide directory",
                },
            )
        ]
    )
    client = FakeClient(response)
    llm = _llm(tmp_path, client)

    result = llm.classify_directory(["https://acmetech.edu/faculty"], _school())

    assert result["directory_urls"] == ["https://acmetech.edu/faculty"]
    assert result["confidence"] == 0.9
    assert result["notes"] == "campus-wide directory"
    assert len(client.messages.calls) == 1
    call = client.messages.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": TOOL_NAME}
    assert call["model"] == "claude-sonnet-5"


def test_response_is_cached_by_prompt_hash(tmp_path: Path) -> None:
    response = FakeResponse(
        [FakeToolUseBlock(TOOL_NAME, {"directory_urls": [], "confidence": 0, "notes": ""})]
    )
    client = FakeClient(response)
    llm = _llm(tmp_path, client)
    candidates = ["https://acmetech.edu/faculty"]

    llm.classify_directory(candidates, _school())
    llm.classify_directory(candidates, _school())

    assert len(client.messages.calls) == 1


def test_confidence_is_clamped_to_unit_interval(tmp_path: Path) -> None:
    response = FakeResponse(
        [
            FakeToolUseBlock(
                TOOL_NAME, {"directory_urls": ["https://x.edu/f"], "confidence": 5, "notes": ""}
            )
        ]
    )
    llm = _llm(tmp_path, FakeClient(response))

    result = llm.classify_directory(["https://x.edu/f"], _school())

    assert result["confidence"] == 1.0


def test_empty_directory_urls_forces_zero_confidence(tmp_path: Path) -> None:
    response = FakeResponse(
        [
            FakeToolUseBlock(
                TOOL_NAME, {"directory_urls": [], "confidence": 0.8, "notes": "nothing qualifies"}
            )
        ]
    )
    llm = _llm(tmp_path, FakeClient(response))

    result = llm.classify_directory(["https://x.edu/f"], _school())

    assert result["directory_urls"] == []
    assert result["confidence"] == 0.0


def test_refusal_stop_reason_raises_llm_error(tmp_path: Path) -> None:
    response = FakeResponse([], stop_reason="refusal")
    llm = _llm(tmp_path, FakeClient(response))

    with pytest.raises(LLMError):
        llm.classify_directory(["https://x.edu/f"], _school())


def test_no_tool_use_block_raises_llm_error(tmp_path: Path) -> None:
    response = FakeResponse([FakeTextBlock("no tool call")])
    llm = _llm(tmp_path, FakeClient(response))

    with pytest.raises(LLMError):
        llm.classify_directory(["https://x.edu/f"], _school())


def test_transport_error_is_wrapped_as_llm_error(tmp_path: Path) -> None:
    llm = _llm(tmp_path, FakeClient(exc=RuntimeError("connection reset")))

    with pytest.raises(LLMError):
        llm.classify_directory(["https://x.edu/f"], _school())


# -- page excerpts as evidence (M3b) ------------------------------------------


def test_prompt_includes_the_page_excerpt_for_each_candidate(tmp_path: Path) -> None:
    response = FakeResponse(
        [FakeToolUseBlock(TOOL_NAME, {"directory_urls": [], "confidence": 0, "notes": ""})]
    )
    client = FakeClient(response)
    llm = _llm(tmp_path, client)
    url = "https://acmetech.edu/faculty"

    llm.classify_directory([url], _school(), excerpts={url: "Jane Doe, Professor"})

    prompt = client.messages.calls[0]["messages"][0]["content"]
    assert "Jane Doe, Professor" in prompt
    assert url in prompt


def test_missing_excerpt_falls_back_to_url_only_without_crashing(tmp_path: Path) -> None:
    response = FakeResponse(
        [FakeToolUseBlock(TOOL_NAME, {"directory_urls": [], "confidence": 0, "notes": ""})]
    )
    client = FakeClient(response)
    llm = _llm(tmp_path, client)
    url = "https://acmetech.edu/faculty"

    # No excerpts dict at all -- e.g. a search-provided candidate that never
    # went through the resolve-check's fetch.
    result = llm.classify_directory([url], _school())

    assert result == {"directory_urls": [], "confidence": 0.0, "notes": None}
    prompt = client.messages.calls[0]["messages"][0]["content"]
    assert url in prompt
    assert "judge from the URL alone" in prompt


def test_empty_string_excerpt_also_falls_back_to_url_only(tmp_path: Path) -> None:
    response = FakeResponse(
        [FakeToolUseBlock(TOOL_NAME, {"directory_urls": [], "confidence": 0, "notes": ""})]
    )
    client = FakeClient(response)
    llm = _llm(tmp_path, client)
    url = "https://acmetech.edu/faculty"

    llm.classify_directory([url], _school(), excerpts={url: "   "})

    prompt = client.messages.calls[0]["messages"][0]["content"]
    assert "judge from the URL alone" in prompt


def test_different_excerpts_change_the_cache_key(tmp_path: Path) -> None:
    """Response caching is by prompt hash (§5.5); since the excerpt is now
    part of the prompt, two different excerpts for the same URL must not
    collide in the cache."""
    response_a = FakeResponse(
        [FakeToolUseBlock(TOOL_NAME, {"directory_urls": [], "confidence": 0, "notes": "a"})]
    )
    url = "https://acmetech.edu/faculty"
    prompts_dir = _prompts_dir(tmp_path)

    client_a = FakeClient(response_a)
    llm_a = AnthropicLLM(_config(tmp_path), client=client_a, prompts_dir=prompts_dir)
    result_a = llm_a.classify_directory([url], _school(), excerpts={url: "excerpt one"})

    response_b = FakeResponse(
        [FakeToolUseBlock(TOOL_NAME, {"directory_urls": [], "confidence": 0, "notes": "b"})]
    )
    client_b = FakeClient(response_b)
    llm_b = AnthropicLLM(_config(tmp_path), client=client_b, prompts_dir=prompts_dir)
    result_b = llm_b.classify_directory([url], _school(), excerpts={url: "excerpt two"})

    assert len(client_a.messages.calls) == 1
    assert len(client_b.messages.calls) == 1
    assert result_a["notes"] == "a"
    assert result_b["notes"] == "b"
