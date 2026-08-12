from __future__ import annotations

from pathlib import Path

import pytest

from faculty_pipeline.config import Config
from faculty_pipeline.models import School
from faculty_pipeline.services import llm
from faculty_pipeline.services.llm import (
    EXTRACT_TOOL_NAME,
    TOOL_NAME,
    AnthropicLLM,
    ExtractionFailed,
    LLMError,
)


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
    (prompts / "extract_professor.txt").write_text(
        "school={school_name} home={homepage} url={url}\n"
        "hints:\n{hints_block}\n"
        "text:\n{page_text}\n",
        encoding="utf-8",
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
    def __init__(
        self,
        response: FakeResponse | None = None,
        exc: Exception | None = None,
        responses: list[FakeResponse] | None = None,
    ) -> None:
        self._response = response
        self._exc = exc
        self._responses = list(responses) if responses is not None else None
        self.calls: list[dict] = []

    def create(self, **kwargs: object) -> FakeResponse:
        self.calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        if self._responses is not None:
            return self._responses.pop(0)
        assert self._response is not None
        return self._response


class FakeClient:
    def __init__(
        self,
        response: FakeResponse | None = None,
        exc: Exception | None = None,
        responses: list[FakeResponse] | None = None,
    ) -> None:
        self.messages = FakeMessages(response, exc, responses)


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


# -- extract_professor (M5) --------------------------------------------------


def _valid_extraction_input(**overrides: object) -> dict:
    defaults: dict[str, object] = dict(
        is_profile=True,
        professor_name="Jane Doe",
        title="Professor of Biology",
        department="Biology",
        email="jane.doe@acmetech.edu",
        phone=None,
        research_interests="genomics; evolutionary biology",
        confidence=0.9,
        notes="clear individual profile",
    )
    defaults.update(overrides)
    return defaults


def test_extract_professor_returns_structured_result(tmp_path: Path) -> None:
    response = FakeResponse(
        [FakeToolUseBlock(EXTRACT_TOOL_NAME, _valid_extraction_input())]
    )
    client = FakeClient(response)
    llm = _llm(tmp_path, client)

    result = llm.extract_professor(
        "Jane Doe, Professor of Biology", "https://x.edu/jane", _school()
    )

    assert result["is_profile"] is True
    assert result["professor_name"] == "Jane Doe"
    assert result["email"] == "jane.doe@acmetech.edu"
    assert result["confidence"] == 0.9
    assert len(client.messages.calls) == 1
    call = client.messages.calls[0]
    assert call["tool_choice"] == {"type": "tool", "name": EXTRACT_TOOL_NAME}
    assert call["model"] == "claude-sonnet-5"


def test_extract_professor_prompt_includes_hints_and_text(tmp_path: Path) -> None:
    response = FakeResponse([FakeToolUseBlock(EXTRACT_TOOL_NAME, _valid_extraction_input())])
    client = FakeClient(response)
    llm = _llm(tmp_path, client)

    llm.extract_professor(
        "Jane Doe is a professor.",
        "https://x.edu/jane",
        _school(),
        hints={"email": "jane.doe@acmetech.edu", "title_hint": "Jane Doe | Acme Tech"},
    )

    prompt = client.messages.calls[0]["messages"][0]["content"]
    assert "jane.doe@acmetech.edu" in prompt
    assert "Jane Doe | Acme Tech" in prompt
    assert "Jane Doe is a professor." in prompt


def test_extract_professor_no_hints_renders_placeholder(tmp_path: Path) -> None:
    response = FakeResponse([FakeToolUseBlock(EXTRACT_TOOL_NAME, _valid_extraction_input())])
    client = FakeClient(response)
    llm = _llm(tmp_path, client)

    llm.extract_professor("text", "https://x.edu/jane", _school())

    prompt = client.messages.calls[0]["messages"][0]["content"]
    assert "no deterministic hints" in prompt


def test_extract_professor_is_profile_false_forces_null_fields(tmp_path: Path) -> None:
    raw = dict(
        is_profile=False,
        professor_name="Directory Index",  # model should not do this, but coercion must win
        title="whatever",
        department="whatever",
        email="fake@x.edu",
        phone="555-0000",
        research_interests="whatever",
        confidence=0.7,
        notes="this is a directory listing, not a person",
    )
    response = FakeResponse([FakeToolUseBlock(EXTRACT_TOOL_NAME, raw)])
    llm = _llm(tmp_path, FakeClient(response))

    result = llm.extract_professor("text", "https://x.edu/dir", _school())

    assert result["is_profile"] is False
    assert result["professor_name"] is None
    assert result["email"] is None
    assert result["phone"] is None
    assert result["confidence"] == 0.0


def test_extract_professor_response_is_cached_by_prompt_hash(tmp_path: Path) -> None:
    response = FakeResponse([FakeToolUseBlock(EXTRACT_TOOL_NAME, _valid_extraction_input())])
    client = FakeClient(response)
    llm = _llm(tmp_path, client)

    llm.extract_professor("text", "https://x.edu/jane", _school())
    llm.extract_professor("text", "https://x.edu/jane", _school())

    assert len(client.messages.calls) == 1


def test_extract_professor_refusal_raises_llm_error(tmp_path: Path) -> None:
    response = FakeResponse([], stop_reason="refusal")
    llm = _llm(tmp_path, FakeClient(response))

    with pytest.raises(LLMError):
        llm.extract_professor("text", "https://x.edu/jane", _school())


def test_extract_professor_transport_error_is_wrapped_as_llm_error(tmp_path: Path) -> None:
    llm = _llm(tmp_path, FakeClient(exc=RuntimeError("connection reset")))

    with pytest.raises(LLMError):
        llm.extract_professor("text", "https://x.edu/jane", _school())


def test_extract_professor_repairs_a_missing_field_then_succeeds(tmp_path: Path) -> None:
    bad_raw = _valid_extraction_input()
    del bad_raw["professor_name"]  # missing required field -> repairable
    bad_response = FakeResponse([FakeToolUseBlock(EXTRACT_TOOL_NAME, bad_raw)])
    good_response = FakeResponse([FakeToolUseBlock(EXTRACT_TOOL_NAME, _valid_extraction_input())])
    client = FakeClient(responses=[bad_response, good_response])
    llm = _llm(tmp_path, client)

    result = llm.extract_professor("text", "https://x.edu/jane", _school())

    assert result["professor_name"] == "Jane Doe"
    assert len(client.messages.calls) == 2
    # The repair call replays the assistant's bad tool call plus a
    # corrective instruction, on top of the original user prompt.
    second_messages = client.messages.calls[1]["messages"]
    assert len(second_messages) == 3
    assert second_messages[0]["role"] == "user"
    assert second_messages[1]["role"] == "assistant"
    assert second_messages[2]["role"] == "user"
    assert "invalid" in second_messages[2]["content"].lower()


def test_extract_professor_is_profile_true_without_name_is_repairable(tmp_path: Path) -> None:
    bad_raw = _valid_extraction_input(professor_name=None)
    bad_response = FakeResponse([FakeToolUseBlock(EXTRACT_TOOL_NAME, bad_raw)])
    good_response = FakeResponse([FakeToolUseBlock(EXTRACT_TOOL_NAME, _valid_extraction_input())])
    client = FakeClient(responses=[bad_response, good_response])
    llm = _llm(tmp_path, client)

    result = llm.extract_professor("text", "https://x.edu/jane", _school())

    assert result["professor_name"] == "Jane Doe"
    assert len(client.messages.calls) == 2


def test_extract_professor_gives_up_after_one_repair_retry(tmp_path: Path) -> None:
    bad_raw = _valid_extraction_input()
    del bad_raw["professor_name"]
    bad_response = FakeResponse([FakeToolUseBlock(EXTRACT_TOOL_NAME, bad_raw)])
    still_bad_response = FakeResponse([FakeToolUseBlock(EXTRACT_TOOL_NAME, bad_raw)])
    client = FakeClient(responses=[bad_response, still_bad_response])
    llm = _llm(tmp_path, client)

    with pytest.raises(ExtractionFailed):
        llm.extract_professor("text", "https://x.edu/jane", _school())

    assert len(client.messages.calls) == 2  # initial attempt + exactly one repair retry


def test_extract_professor_no_tool_use_block_triggers_repair(tmp_path: Path) -> None:
    no_tool_response = FakeResponse([FakeTextBlock("I refuse to call a tool")])
    good_response = FakeResponse([FakeToolUseBlock(EXTRACT_TOOL_NAME, _valid_extraction_input())])
    client = FakeClient(responses=[no_tool_response, good_response])
    llm = _llm(tmp_path, client)

    result = llm.extract_professor("text", "https://x.edu/jane", _school())

    assert result["professor_name"] == "Jane Doe"
    assert len(client.messages.calls) == 2


class TestIsFacultyCoercion:
    """`is_faculty` is three-valued on purpose: true, false, and "the page
    doesn't say". Coercing an unknown to `false` would quietly drop real
    professors, which is the one direction this pipeline must not fail in."""

    def test_true_survives(self):
        raw = _extract_payload(is_faculty=True)

        assert llm._coerce_extraction(raw)["is_faculty"] is True

    def test_false_survives(self):
        raw = _extract_payload(is_faculty=False)

        assert llm._coerce_extraction(raw)["is_faculty"] is False

    def test_null_stays_null(self):
        raw = _extract_payload(is_faculty=None)

        assert llm._coerce_extraction(raw)["is_faculty"] is None

    def test_a_missing_key_is_unknown_not_false(self):
        """Extractions cached before this field existed have no key at all."""
        raw = _extract_payload()
        raw.pop("is_faculty", None)

        assert llm._coerce_extraction(raw)["is_faculty"] is None

    def test_a_non_boolean_is_unknown_not_false(self):
        raw = _extract_payload(is_faculty="yes")

        assert llm._coerce_extraction(raw)["is_faculty"] is None

    def test_a_non_profile_carries_no_judgment(self):
        raw = _extract_payload(is_faculty=True)
        raw["is_profile"] = False

        assert llm._coerce_extraction(raw)["is_faculty"] is None


def _extract_payload(**overrides: object) -> dict:
    payload = {
        "is_profile": True,
        "professor_name": "Jane Doe",
        "title": "Professor of Biology",
        "is_faculty": True,
        "department": "Biology",
        "email": None,
        "phone": None,
        "research_interests": None,
        "confidence": 0.9,
        "notes": "clear profile",
    }
    payload.update(overrides)
    return payload
