"""Fetches and caches each host's robots.txt; exposes `is_allowed(url, agent)`
and `crawl_delay(url)` so the rate limiter in http_client.py can honor it
(§5.3).

This is the gate that makes the crawler polite: `http_client.HttpClient`
refuses a disallowed URL outright (raises `RobotsDisallowedError`) rather than
logging and continuing.
"""
from __future__ import annotations

import urllib.robotparser
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

DEFAULT_ROBOTS_TIMEOUT = 10.0


class RobotsDisallowedError(RuntimeError):
    """Raised when a URL is disallowed by the target host's robots.txt."""

    def __init__(self, url: str) -> None:
        super().__init__(f"fetching disallowed by robots.txt: {url}")
        self.url = url


class RobotsResponse(Protocol):
    status_code: int
    text: str


class RobotsTransport(Protocol):
    """The subset of `httpx.Client` robots.py needs. A Protocol (rather than a
    concrete `httpx.Client` type hint) so tests can inject a plain fake
    without constructing real `httpx.Response` objects."""

    def get(self, url: str, *, timeout: float) -> RobotsResponse: ...


@dataclass
class _HostRules:
    parser: urllib.robotparser.RobotFileParser
    crawl_delay: float | None


class RobotsChecker:
    """Per-host robots.txt cache. A host is fetched at most once per process
    lifetime; fetch failures (network error, 4xx/5xx) default to "allowed,
    no crawl-delay" per standard robots.txt convention (missing robots.txt
    means no restrictions)."""

    def __init__(
        self,
        transport: RobotsTransport,
        timeout: float = DEFAULT_ROBOTS_TIMEOUT,
    ) -> None:
        self._transport = transport
        self._timeout = timeout
        self._cache: dict[str, _HostRules | None] = {}

    def is_allowed(self, url: str, user_agent: str) -> bool:
        rules = self._get_rules(url)
        if rules is None:
            return True
        return rules.parser.can_fetch(user_agent, url)

    def crawl_delay(self, url: str) -> float | None:
        rules = self._get_rules(url)
        return rules.crawl_delay if rules is not None else None

    def _get_rules(self, url: str) -> _HostRules | None:
        parsed = urlparse(url)
        host_key = f"{parsed.scheme}://{parsed.netloc}"
        if host_key in self._cache:
            return self._cache[host_key]

        robots_url = f"{host_key}/robots.txt"
        rules: _HostRules | None
        try:
            response = self._transport.get(robots_url, timeout=self._timeout)
        except Exception:  # noqa: BLE001 - any transport error => can't fetch robots.txt
            rules = None
        else:
            if response.status_code >= 400:
                rules = None
            else:
                parser = urllib.robotparser.RobotFileParser()
                parser.parse(response.text.splitlines())
                rules = _HostRules(parser=parser, crawl_delay=parser.crawl_delay("*"))

        self._cache[host_key] = rules
        return rules
