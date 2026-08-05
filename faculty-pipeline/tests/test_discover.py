from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from faculty_pipeline.config import Config
from faculty_pipeline.models import School
from faculty_pipeline.services.checkpoint import CheckpointStore
from faculty_pipeline.services.http_client import FetchResult
from faculty_pipeline.services.robots import RobotsDisallowedError
from faculty_pipeline.services.search import NullSearchProvider, SearchResult
from faculty_pipeline.stages import discover

HTML_OK = "<html><body><h1>Faculty Directory</h1><p>Jane Doe, Professor</p></body></html>"
HTML_SOFT_404 = (
    "<html><body><h1>Page Not Found</h1><p>Sorry, we couldn't find that page.</p></body></html>"
)


def _school(school_id: str = "acme-tech", homepage: str = "https://www.acmetech.edu") -> School:
    return School(
        school_id=school_id,
        name="Acme Tech",
        slug=school_id,
        country="US",
        homepage=homepage,
    )


def _config(tmp_path: Path) -> Config:
    return Config(
        input_path=tmp_path / "schools.json",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        checkpoint_dir=tmp_path / "checkpoints",
        log_dir=tmp_path / "logs",
    )


def _write_schools(config: Config, schools: list[School]) -> None:
    path = Path(config.data_dir) / "schools.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(s.model_dump_json() for s in schools) + "\n", encoding="utf-8")


def _fetch_result(status: int, body: str, url: str) -> FetchResult:
    return FetchResult(
        status=status, final_url=url, body=body, from_cache=False, cache_path=Path("/dev/null")
    )


@dataclass
class FakeHttpClient:
    """Maps url -> FetchResult; unmapped URLs raise (treated as a fetch
    failure, same as a real dead heuristic link)."""

    pages: dict[str, FetchResult] = field(default_factory=dict)
    disallowed: set[str] = field(default_factory=set)
    calls: list[str] = field(default_factory=list)

    def fetch(self, url: str, *, method: str = "GET") -> FetchResult:
        self.calls.append(url)
        if url in self.disallowed:
            raise RobotsDisallowedError(url)
        if url in self.pages:
            return self.pages[url]
        raise RuntimeError(f"no fixture for {url}")


@dataclass
class FakeSearchProvider:
    results: list[SearchResult] = field(default_factory=list)
    error: Exception | None = None
    calls: list[str] = field(default_factory=list)

    def search(self, query: str) -> list[SearchResult]:
        self.calls.append(query)
        if self.error is not None:
            raise self.error
        return self.results


@dataclass
class FakeLLM:
    response: dict | None = None
    error: Exception | None = None
    calls: list[tuple[tuple[str, ...], str]] = field(default_factory=list)

    def classify_directory(self, candidates: list[str], school: School) -> dict:
        self.calls.append((tuple(candidates), school.school_id))
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


class AllowAllRobots:
    def is_allowed(self, url: str, user_agent: str) -> bool:
        return True

    def crawl_delay(self, url: str) -> float | None:
        return None


@dataclass
class SelectiveRobots:
    disallowed: set[str] = field(default_factory=set)

    def is_allowed(self, url: str, user_agent: str) -> bool:
        return url not in self.disallowed

    def crawl_delay(self, url: str) -> float | None:
        return None


def _run(
    config: Config,
    checkpoint: CheckpointStore,
    http_client: FakeHttpClient,
    search_provider: object,
    llm: object,
    robots: object,
    **kwargs: object,
):
    logger = logging.getLogger("faculty_pipeline.test_discover")
    return discover.run(
        config, checkpoint, logger, http_client, search_provider, llm, robots, **kwargs
    )


def _checkpoint(config: Config) -> CheckpointStore:
    return CheckpointStore(Path(config.checkpoint_dir) / "discover.json")


def _read_output(config: Config) -> list[dict]:
    path = Path(config.data_dir) / "directories.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# -- heuristic hit ----------------------------------------------------------


def test_heuristic_hit_is_classified_and_recorded(tmp_path: Path) -> None:
    config = _config(tmp_path)
    school = _school()
    _write_schools(config, [school])
    url = "https://www.acmetech.edu/faculty"
    http_client = FakeHttpClient(pages={url: _fetch_result(200, HTML_OK, url)})
    llm = FakeLLM(response={"directory_urls": [url], "confidence": 0.95, "notes": "campus-wide"})

    summary = _run(
        config, _checkpoint(config), http_client, NullSearchProvider(), llm, AllowAllRobots()
    )

    rows = _read_output(config)
    assert len(rows) == 1
    assert rows[0]["directory_urls"] == [url]
    assert rows[0]["discovery_method"] == "heuristic"
    assert rows[0]["robots_allowed"] is True
    assert rows[0]["confidence"] == 0.95
    assert summary.processed == 1
    assert summary.failed == 0
    assert _checkpoint(config).is_done(school.school_id) is True
    assert llm.calls == [((url,), school.school_id)]


# -- soft-404 rejection -------------------------------------------------------


def test_soft_404_heuristic_candidate_is_rejected(tmp_path: Path) -> None:
    config = _config(tmp_path)
    school = _school()
    _write_schools(config, [school])
    url = "https://www.acmetech.edu/faculty"
    http_client = FakeHttpClient(pages={url: _fetch_result(200, HTML_SOFT_404, url)})
    llm = FakeLLM()

    _run(config, _checkpoint(config), http_client, NullSearchProvider(), llm, AllowAllRobots())

    rows = _read_output(config)
    assert len(rows) == 1
    assert rows[0]["directory_urls"] == []
    assert rows[0]["confidence"] == 0.0
    assert rows[0]["discovery_method"] == "none"
    # A soft-404'd candidate never survives to be handed to the LLM.
    assert llm.calls == []


# -- empty-result-is-done ----------------------------------------------------


def test_no_candidates_at_all_is_marked_done_not_failed(tmp_path: Path) -> None:
    config = _config(tmp_path)
    school = _school()
    _write_schools(config, [school])
    http_client = FakeHttpClient(pages={})  # every heuristic URL fails to fetch
    llm = FakeLLM()

    summary = _run(
        config, _checkpoint(config), http_client, NullSearchProvider(), llm, AllowAllRobots()
    )

    rows = _read_output(config)
    assert rows[0]["directory_urls"] == []
    assert rows[0]["confidence"] == 0.0
    assert summary.failed == 0
    assert summary.processed == 1
    assert _checkpoint(config).is_done(school.school_id) is True


# -- aggregator rejection -----------------------------------------------------


def test_aggregator_candidate_not_selected_by_llm_is_excluded(tmp_path: Path) -> None:
    config = _config(tmp_path)
    school = _school()
    _write_schools(config, [school])
    official = "https://www.acmetech.edu/faculty"
    aggregator = "https://www.ratemyprofessors.com/school/12345"
    http_client = FakeHttpClient(
        pages={
            official: _fetch_result(200, HTML_OK, official),
        }
    )
    search_provider = FakeSearchProvider(
        results=[SearchResult(url=aggregator, title="Acme Tech - RateMyProfessors")]
    )
    http_client.pages[aggregator] = _fetch_result(
        200, "<html><body>Professor ratings</body></html>", aggregator
    )
    llm = FakeLLM(
        response={
            "directory_urls": [official],
            "confidence": 0.9,
            "notes": "rejected RateMyProfessors as a third-party aggregator",
        }
    )

    _run(config, _checkpoint(config), http_client, search_provider, llm, AllowAllRobots())

    rows = _read_output(config)
    assert rows[0]["directory_urls"] == [official]
    assert aggregator not in rows[0]["directory_urls"]
    assert rows[0]["discovery_method"] == "heuristic+search"
    # The LLM was shown both candidates, and chose to keep only one.
    (candidates_seen, _school_id) = llm.calls[0]
    assert aggregator in candidates_seen
    assert official in candidates_seen


def test_llm_invented_url_outside_candidate_set_is_dropped(tmp_path: Path) -> None:
    """Trust boundary: the LLM's output is untrusted. A URL that wasn't in
    the candidate list it was given must never be accepted, even if the
    model returns it."""
    config = _config(tmp_path)
    school = _school()
    _write_schools(config, [school])
    official = "https://www.acmetech.edu/faculty"
    invented = "https://evil.example.com/not-a-real-candidate"
    http_client = FakeHttpClient(pages={official: _fetch_result(200, HTML_OK, official)})
    llm = FakeLLM(response={"directory_urls": [official, invented], "confidence": 0.9, "notes": ""})

    _run(config, _checkpoint(config), http_client, NullSearchProvider(), llm, AllowAllRobots())

    rows = _read_output(config)
    assert rows[0]["directory_urls"] == [official]
    assert invented not in rows[0]["directory_urls"]
    assert "dropped 1 LLM-suggested URL" in (rows[0]["notes"] or "")


# -- robots-disallowed handling -----------------------------------------------


def test_robots_disallowed_heuristic_candidate_is_excluded_not_errored(tmp_path: Path) -> None:
    config = _config(tmp_path)
    school = _school()
    _write_schools(config, [school])
    disallowed_url = "https://www.acmetech.edu/faculty"
    http_client = FakeHttpClient(disallowed={disallowed_url})
    llm = FakeLLM()

    summary = _run(
        config, _checkpoint(config), http_client, NullSearchProvider(), llm, AllowAllRobots()
    )

    rows = _read_output(config)
    assert rows[0]["directory_urls"] == []
    assert summary.failed == 0
    assert llm.calls == []  # never reached the LLM: no surviving candidates


def test_robots_disallows_the_llm_chosen_url_after_selection(tmp_path: Path) -> None:
    config = _config(tmp_path)
    school = _school()
    _write_schools(config, [school])
    chosen = "https://www.acmetech.edu/faculty"
    http_client = FakeHttpClient(pages={chosen: _fetch_result(200, HTML_OK, chosen)})
    llm = FakeLLM(response={"directory_urls": [chosen], "confidence": 0.9, "notes": ""})
    robots = SelectiveRobots(disallowed={chosen})

    _run(config, _checkpoint(config), http_client, NullSearchProvider(), llm, robots)

    rows = _read_output(config)
    assert rows[0]["directory_urls"] == []
    assert rows[0]["robots_allowed"] is False
    assert rows[0]["confidence"] == 0.0
    assert "robots.txt" in (rows[0]["notes"] or "")


# -- no-search-provider path (SEARCH_API_KEY unset -> NullSearchProvider) ----


def test_null_search_provider_degrades_gracefully(tmp_path: Path) -> None:
    config = _config(tmp_path)
    school = _school()
    _write_schools(config, [school])
    url = "https://www.acmetech.edu/faculty"
    http_client = FakeHttpClient(pages={url: _fetch_result(200, HTML_OK, url)})
    llm = FakeLLM(response={"directory_urls": [url], "confidence": 0.9, "notes": ""})

    _run(config, _checkpoint(config), http_client, NullSearchProvider(), llm, AllowAllRobots())

    rows = _read_output(config)
    assert rows[0]["discovery_method"] == "heuristic"  # search contributed nothing, never raised


# -- checkpoint skip / retry --------------------------------------------------


def test_already_done_school_is_skipped(tmp_path: Path) -> None:
    config = _config(tmp_path)
    school = _school()
    _write_schools(config, [school])
    checkpoint = _checkpoint(config)
    checkpoint.mark_done(school.school_id, meta={"directory_urls": []})
    http_client = FakeHttpClient()
    llm = FakeLLM()

    summary = _run(config, checkpoint, http_client, NullSearchProvider(), llm, AllowAllRobots())

    assert summary.processed == 0
    assert summary.skipped == 1
    assert http_client.calls == []
    assert llm.calls == []


def test_search_error_marks_school_failed_and_retried_next_run(tmp_path: Path) -> None:
    config = _config(tmp_path)
    school = _school()
    _write_schools(config, [school])
    checkpoint = _checkpoint(config)
    http_client = FakeHttpClient()  # every heuristic URL fails -> falls through to search
    failing_search = FakeSearchProvider(error=RuntimeError("search API down"))

    summary = _run(config, checkpoint, http_client, failing_search, FakeLLM(), AllowAllRobots())

    assert summary.failed == 1
    assert checkpoint.is_done(school.school_id) is False
    assert _read_output(config) == []  # nothing written for a failed school

    # Next run retries it: this time search succeeds with no results.
    working_search = FakeSearchProvider(results=[])
    summary2 = _run(config, checkpoint, http_client, working_search, FakeLLM(), AllowAllRobots())

    assert summary2.processed == 1
    assert summary2.failed == 0
    assert checkpoint.is_done(school.school_id) is True


def test_llm_error_marks_school_failed_not_done(tmp_path: Path) -> None:
    config = _config(tmp_path)
    school = _school()
    _write_schools(config, [school])
    checkpoint = _checkpoint(config)
    url = "https://www.acmetech.edu/faculty"
    http_client = FakeHttpClient(pages={url: _fetch_result(200, HTML_OK, url)})
    llm = FakeLLM(error=RuntimeError("anthropic API 500"))

    summary = _run(config, checkpoint, http_client, NullSearchProvider(), llm, AllowAllRobots())

    assert summary.failed == 1
    assert checkpoint.is_done(school.school_id) is False
    assert _read_output(config) == []


# -- limit / school filters ---------------------------------------------------


def test_limit_caps_number_of_schools_processed(tmp_path: Path) -> None:
    config = _config(tmp_path)
    schools = [_school(f"acme-{i}", f"https://www{i}.acmetech.edu") for i in range(3)]
    _write_schools(config, schools)
    http_client = FakeHttpClient()
    llm = FakeLLM()

    summary = _run(
        config,
        _checkpoint(config),
        http_client,
        NullSearchProvider(),
        llm,
        AllowAllRobots(),
        limit=1,
    )

    assert summary.processed == 1
    assert summary.skipped == 2


def test_school_filter_forces_reprocessing_even_if_done(tmp_path: Path) -> None:
    config = _config(tmp_path)
    school = _school()
    _write_schools(config, [school])
    checkpoint = _checkpoint(config)
    checkpoint.mark_done(school.school_id, meta={"directory_urls": []})
    http_client = FakeHttpClient()
    llm = FakeLLM()

    summary = _run(
        config,
        checkpoint,
        http_client,
        NullSearchProvider(),
        llm,
        AllowAllRobots(),
        school_id=school.school_id,
    )

    assert summary.processed == 1  # explicit --school reprocesses despite being done


# -- dry run ------------------------------------------------------------------


def test_dry_run_makes_no_network_or_llm_calls_and_writes_nothing(tmp_path: Path) -> None:
    config = _config(tmp_path)
    school = _school()
    _write_schools(config, [school])
    http_client = FakeHttpClient()
    llm = FakeLLM()

    summary = _run(
        config,
        _checkpoint(config),
        http_client,
        NullSearchProvider(),
        llm,
        AllowAllRobots(),
        dry_run=True,
    )

    assert http_client.calls == []
    assert llm.calls == []
    assert _read_output(config) == []
    assert _checkpoint(config).is_done(school.school_id) is False
    assert summary.processed == 0
    assert "would process 1 school" in summary.notes[0]
