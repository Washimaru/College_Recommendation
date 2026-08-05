from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from faculty_pipeline.config import Config
from faculty_pipeline.services.http_client import HttpClient
from faculty_pipeline.services.robots import RobotsDisallowedError


def make_config(tmp_path: Path, **overrides: object) -> Config:
    defaults: dict[str, object] = dict(
        input_path=tmp_path / "schools.json",
        cache_dir=tmp_path / "cache",
        checkpoint_dir=tmp_path / "checkpoints",
        log_dir=tmp_path / "logs",
        data_dir=tmp_path / "data",
        output_dir=tmp_path / "output",
        rate_limit_per_host=0.0,  # tests don't want real waits
        max_retries=3,
        respect_robots=True,
        user_agent="UniMatchFacultyBot/0.1 (+test)",
    )
    defaults.update(overrides)
    return Config(**defaults)  # type: ignore[arg-type]


@dataclass
class FakeResponse:
    status_code: int
    text: str
    url: str = "https://example.edu/faculty/"
    headers: dict[str, str] = field(default_factory=dict)


class FakeTransport:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def request(self, method: str, url: str, *, headers: dict[str, str], timeout: float):
        self.calls.append((method, url))
        if not self._responses:
            raise AssertionError("transport called more times than expected responses queued")
        return self._responses.pop(0)


class AllowAllRobots:
    def is_allowed(self, url: str, user_agent: str) -> bool:
        return True

    def crawl_delay(self, url: str) -> float | None:
        return None


class DisallowAllRobots:
    def is_allowed(self, url: str, user_agent: str) -> bool:
        return False

    def crawl_delay(self, url: str) -> float | None:
        return None


class NoSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def test_disallowed_url_is_refused_without_touching_transport(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    transport = FakeTransport([])
    client = HttpClient(config, DisallowAllRobots(), transport, sleep_fn=NoSleep())

    with pytest.raises(RobotsDisallowedError):
        client.fetch("https://example.edu/faculty/")

    assert transport.calls == []


def test_cache_hit_never_calls_transport(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    url = "https://example.edu/faculty/"

    # First fetch: populates the cache.
    transport = FakeTransport([FakeResponse(200, "<html>faculty</html>", url=url)])
    client = HttpClient(config, AllowAllRobots(), transport, sleep_fn=NoSleep())
    first = client.fetch(url)
    assert first.from_cache is False
    assert transport.calls == [("GET", url)]

    # Second fetch, fresh client/transport: must be served from cache, zero
    # network calls, per §5.2 "cache checked before the network".
    empty_transport = FakeTransport([])
    second_client = HttpClient(config, AllowAllRobots(), empty_transport, sleep_fn=NoSleep())
    second = second_client.fetch(url)

    assert second.from_cache is True
    assert second.body == "<html>faculty</html>"
    assert empty_transport.calls == []


def test_successful_fetch_is_written_to_cache_dir(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    url = "https://example.edu/faculty/"
    transport = FakeTransport([FakeResponse(200, "hello", url=url)])
    client = HttpClient(config, AllowAllRobots(), transport, sleep_fn=NoSleep())

    result = client.fetch(url)

    assert result.cache_path.exists()
    assert result.cache_path.read_text() == "hello"


def test_retries_on_5xx_then_succeeds(tmp_path: Path) -> None:
    config = make_config(tmp_path, max_retries=3)
    url = "https://example.edu/faculty/"
    transport = FakeTransport(
        [
            FakeResponse(503, "", url=url),
            FakeResponse(200, "ok", url=url),
        ]
    )
    sleep = NoSleep()
    client = HttpClient(config, AllowAllRobots(), transport, sleep_fn=sleep)

    result = client.fetch(url)

    assert result.status == 200
    assert result.body == "ok"
    assert len(transport.calls) == 2
    assert len(sleep.calls) == 1  # backed off exactly once between attempts


def test_gives_up_after_max_retries(tmp_path: Path) -> None:
    config = make_config(tmp_path, max_retries=2)
    url = "https://example.edu/faculty/"
    transport = FakeTransport([FakeResponse(500, "", url=url), FakeResponse(500, "", url=url)])
    client = HttpClient(config, AllowAllRobots(), transport, sleep_fn=NoSleep())

    result = client.fetch(url)

    assert result.status == 500
    assert len(transport.calls) == 2


def test_rate_limiter_sleeps_for_configured_interval(tmp_path: Path) -> None:
    config = make_config(tmp_path, rate_limit_per_host=2.0)
    transport = FakeTransport(
        [
            FakeResponse(200, "a", url="https://example.edu/1"),
            FakeResponse(200, "b", url="https://example.edu/2"),
        ]
    )
    sleep = NoSleep()
    clock = iter([0.0, 0.0, 0.5, 0.5])  # two calls per fetch: before+after send
    client = HttpClient(
        config, AllowAllRobots(), transport, sleep_fn=sleep, clock_fn=lambda: next(clock)
    )

    client.fetch("https://example.edu/1")
    client.fetch("https://example.edu/2")

    assert sleep.calls == [pytest.approx(1.5)]


def test_rate_limiter_honors_larger_crawl_delay(tmp_path: Path) -> None:
    class SlowCrawlDelayRobots(AllowAllRobots):
        def crawl_delay(self, url: str) -> float | None:
            return 10.0

    config = make_config(tmp_path, rate_limit_per_host=2.0)
    transport = FakeTransport(
        [
            FakeResponse(200, "a", url="https://example.edu/1"),
            FakeResponse(200, "b", url="https://example.edu/2"),
        ]
    )
    sleep = NoSleep()
    clock = iter([0.0, 0.0, 1.0, 1.0])
    client = HttpClient(
        config,
        SlowCrawlDelayRobots(),
        transport,
        sleep_fn=sleep,
        clock_fn=lambda: next(clock),
    )

    client.fetch("https://example.edu/1")
    client.fetch("https://example.edu/2")

    # honors the site's own Crawl-delay (10s) over the configured 2s floor
    assert sleep.calls == [pytest.approx(9.0)]
