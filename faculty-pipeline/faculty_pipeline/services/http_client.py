"""The single fetch path for the whole pipeline (§5.2).

Order of operations for every `fetch()`:

1. Check the HTML cache (keyed by SHA-256 of the URL). Hit => return
   immediately, no network call.
2. Check `robots.py`. Disallowed => raise `RobotsDisallowedError`, never
   "log and continue".
3. Acquire a per-host rate-limit slot, honoring the larger of the configured
   `rate_limit_per_host` and the host's own `Crawl-delay`.
4. Send the request with the configured User-Agent and timeout; retry on
   429/5xx with exponential backoff + jitter, honoring `Retry-After`.
5. Persist the body to the cache and return.
"""
from __future__ import annotations

import json
import random
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

from ..config import Config
from ..utils import sha256_hex
from .robots import RobotsDisallowedError

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

# Backoff tuning. Not config keys (§5.1 doesn't list them) — internal to the
# retry loop, same spirit as the CONFIDENCE_THRESHOLD-style module constants
# elsewhere in this repo.
BACKOFF_BASE_SECONDS = 1.0
BACKOFF_CAP_SECONDS = 30.0
BACKOFF_JITTER_FRACTION = 0.25


@dataclass(frozen=True)
class FetchResult:
    status: int
    final_url: str
    body: str
    from_cache: bool
    cache_path: Path


class HttpResponse(Protocol):
    status_code: int
    text: str
    url: object  # str-able (httpx.URL or plain str)
    headers: Mapping[str, str]


class HttpTransport(Protocol):
    """The subset of `httpx.Client` http_client.py needs. A Protocol so tests
    can inject a fake transport without a real network stack."""

    def request(
        self, method: str, url: str, *, headers: Mapping[str, str], timeout: float
    ) -> HttpResponse: ...


class RobotsCheckerLike(Protocol):
    """The subset of `robots.RobotsChecker` http_client.py needs. A Protocol
    (rather than the concrete class) so tests can inject a fake checker."""

    def is_allowed(self, url: str, user_agent: str) -> bool: ...

    def crawl_delay(self, url: str) -> float | None: ...


class HttpClient:
    def __init__(
        self,
        config: Config,
        robots: RobotsCheckerLike,
        transport: HttpTransport,
        sleep_fn: Callable[[float], None] = time.sleep,
        clock_fn: Callable[[], float] = time.monotonic,
        rng: random.Random | None = None,
    ) -> None:
        self._config = config
        self._robots = robots
        self._transport = transport
        self._sleep = sleep_fn
        self._clock = clock_fn
        self._rng = rng or random.Random()
        self._last_request_at: dict[str, float] = {}
        self._cache_dir = Path(config.cache_dir) / "html"

    def fetch(self, url: str, *, method: str = "GET") -> FetchResult:
        cache_key = sha256_hex(url)
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached

        if self._config.respect_robots and not self._robots.is_allowed(
            url, self._config.user_agent
        ):
            raise RobotsDisallowedError(url)

        self._respect_rate_limit(url)
        response = self._send_with_retry(method, url)

        result = FetchResult(
            status=response.status_code,
            final_url=str(response.url),
            body=response.text,
            from_cache=False,
            cache_path=self._body_path(cache_key),
        )
        self._write_cache(cache_key, url, result)
        return result

    # -- rate limiting -----------------------------------------------------

    def _respect_rate_limit(self, url: str) -> None:
        host = urlparse(url).netloc
        crawl_delay = self._robots.crawl_delay(url) if self._config.respect_robots else None
        min_interval = max(self._config.rate_limit_per_host, crawl_delay or 0.0)

        now = self._clock()
        last = self._last_request_at.get(host)
        if last is not None:
            wait = min_interval - (now - last)
            if wait > 0:
                self._sleep(wait)
        self._last_request_at[host] = self._clock()

    # -- retry ---------------------------------------------------------

    def _send_with_retry(self, method: str, url: str) -> HttpResponse:
        response: HttpResponse | None = None
        last_exc: Exception | None = None

        for attempt in range(1, self._config.max_retries + 1):
            try:
                response = self._transport.request(
                    method,
                    url,
                    headers={"User-Agent": self._config.user_agent},
                    timeout=self._config.request_timeout,
                )
            except Exception as exc:  # noqa: BLE001 - transport errors are retried
                last_exc = exc
                response = None
            else:
                last_exc = None
                if response.status_code not in RETRYABLE_STATUS_CODES:
                    return response

            if attempt < self._config.max_retries:
                retry_after = _parse_retry_after(response) if response is not None else None
                self._sleep(self._backoff_delay(attempt, floor=retry_after))

        if response is not None:
            return response
        assert last_exc is not None
        raise last_exc

    def _backoff_delay(self, attempt: int, floor: float | None) -> float:
        delay = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)))
        jitter = delay * BACKOFF_JITTER_FRACTION * self._rng.random()
        return max(delay + jitter, floor or 0.0)

    # -- cache ---------------------------------------------------------

    def _body_path(self, cache_key: str) -> Path:
        return self._cache_dir / f"{cache_key}.html"

    def _meta_path(self, cache_key: str) -> Path:
        return self._cache_dir / f"{cache_key}.json"

    def _read_cache(self, cache_key: str) -> FetchResult | None:
        body_path = self._body_path(cache_key)
        meta_path = self._meta_path(cache_key)
        if not (body_path.exists() and meta_path.exists()):
            return None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        body = body_path.read_text(encoding="utf-8")
        return FetchResult(
            status=meta["status"],
            final_url=meta["final_url"],
            body=body,
            from_cache=True,
            cache_path=body_path,
        )

    def _write_cache(self, cache_key: str, url: str, result: FetchResult) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._body_path(cache_key).write_text(result.body, encoding="utf-8")
        meta = {
            "url": url,
            "status": result.status,
            "final_url": result.final_url,
            "fetched_at": _now_iso(),
        }
        self._meta_path(cache_key).write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _parse_retry_after(response: HttpResponse) -> float | None:
    raw = response.headers.get("Retry-After") if response.headers else None
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()
