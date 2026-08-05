from __future__ import annotations

from dataclasses import dataclass

import pytest

from faculty_pipeline.services.robots import RobotsChecker

UA = "UniMatchFacultyBot/0.1 (+https://example.com/faculty-pipeline)"


@dataclass
class FakeResponse:
    status_code: int
    text: str


class FakeTransport:
    """Records requested URLs and returns a canned robots.txt body per host."""

    def __init__(self, bodies: dict[str, FakeResponse]) -> None:
        self._bodies = bodies
        self.requested: list[str] = []

    def get(self, url: str, *, timeout: float) -> FakeResponse:
        self.requested.append(url)
        if url not in self._bodies:
            return FakeResponse(status_code=404, text="")
        return self._bodies[url]


DISALLOW_ALL = "User-agent: *\nDisallow: /\n"
ALLOW_WITH_DELAY = "User-agent: *\nDisallow: /private/\nCrawl-delay: 5\n"


def test_disallowed_path_is_refused() -> None:
    transport = FakeTransport({"https://example.edu/robots.txt": FakeResponse(200, DISALLOW_ALL)})
    checker = RobotsChecker(transport)

    assert checker.is_allowed("https://example.edu/faculty/", UA) is False


def test_allowed_path_is_permitted() -> None:
    transport = FakeTransport(
        {"https://example.edu/robots.txt": FakeResponse(200, ALLOW_WITH_DELAY)}
    )
    checker = RobotsChecker(transport)

    assert checker.is_allowed("https://example.edu/faculty/", UA) is True
    assert checker.is_allowed("https://example.edu/private/x", UA) is False


def test_crawl_delay_is_surfaced() -> None:
    transport = FakeTransport(
        {"https://example.edu/robots.txt": FakeResponse(200, ALLOW_WITH_DELAY)}
    )
    checker = RobotsChecker(transport)

    assert checker.crawl_delay("https://example.edu/faculty/") == pytest.approx(5.0)


def test_missing_robots_txt_defaults_to_allowed_no_delay() -> None:
    transport = FakeTransport({})  # 404 for everything
    checker = RobotsChecker(transport)

    assert checker.is_allowed("https://example.edu/faculty/", UA) is True
    assert checker.crawl_delay("https://example.edu/faculty/") is None


def test_transport_error_defaults_to_allowed() -> None:
    class RaisingTransport:
        def get(self, url: str, *, timeout: float) -> FakeResponse:
            raise ConnectionError("dns failure")

    checker = RobotsChecker(RaisingTransport())

    assert checker.is_allowed("https://example.edu/faculty/", UA) is True


def test_robots_txt_fetched_once_per_host() -> None:
    transport = FakeTransport({"https://example.edu/robots.txt": FakeResponse(200, DISALLOW_ALL)})
    checker = RobotsChecker(transport)

    checker.is_allowed("https://example.edu/a", UA)
    checker.is_allowed("https://example.edu/b", UA)
    checker.crawl_delay("https://example.edu/c")

    assert transport.requested == ["https://example.edu/robots.txt"]
