"""Headless-browser rendering for JS-rendered directories (§13, opt-in).

Some directories server-render nothing but a shell — or, worse, render only
their first A-Z section and load the rest by script. Stage 3 detects both
(`needs_dynamic_render`), and with `--dynamic` it re-reads those pages through
a real browser so the same link-enumeration code sees what a visitor sees.

Deliberately narrow:

- **Opt-in.** Nothing here runs without `--dynamic`; Playwright is an optional
  extra (`.[dynamic]`) and its absence is reported as a clear error rather
  than a stack trace.
- **Only where the cheap path failed.** A render costs a browser launch and a
  page load; it happens for the directory pages of schools whose static HTML
  yielded no or partial profile links, never routinely.
- **Already robots-approved.** Every URL rendered here has just been fetched
  successfully through `services.http_client`, which is the component that
  enforces robots. This re-reads the same URL; it never reaches a page the
  normal path would have refused. The per-host delay is applied again anyway,
  because a browser load is a heavier request than a plain GET, not a lighter
  one.
"""
from __future__ import annotations

import logging
import time
from types import TracebackType
from typing import Protocol


class RendererUnavailableError(RuntimeError):
    """Playwright (or its browser binary) isn't installed."""


class Renderer(Protocol):
    """What `stages/crawl.py` needs; a Protocol so tests inject a fake and
    never launch a browser."""

    def render(self, url: str) -> str: ...


# One Playwright instance per process: `sync_playwright().start()` refuses to
# run twice concurrently, so a single renderer is created per crawl run and
# per-call behaviour is a `render()` argument rather than a second instance.


class PlaywrightRenderer:
    """Renders pages with headless Chromium, one browser for the whole run.

    Use as a context manager: the browser is expensive to start and must be
    closed, and a crawl renders several pages per JS-rendered school.
    """

    def __init__(
        self,
        *,
        user_agent: str,
        timeout_seconds: float = 30.0,
        delay_seconds: float = 0.0,
        # "domcontentloaded", not "networkidle": university sites commonly hold
        # a connection open (chat widgets, analytics beacons), so networkidle
        # never fires and every render dies on the timeout instead.
        wait_until: str = "domcontentloaded",
        settle_ms: int = 2000,
        # Per expander click. Short on purpose: a directory with 26 letter
        # tabs would otherwise spend a minute of wall clock on one page.
        click_settle_ms: int = 500,
        expand: bool = True,
        max_expansions: int = 40,
        logger: logging.Logger | None = None,
        sleep_fn=time.sleep,
    ) -> None:
        self._user_agent = user_agent
        self._timeout_ms = int(timeout_seconds * 1000)
        self._delay = delay_seconds
        self._wait_until = wait_until
        self._settle_ms = settle_ms
        self._click_settle_ms = click_settle_ms
        self._expand = expand
        self._max_expansions = max_expansions
        self._logger = logger or logging.getLogger(__name__)
        self._sleep = sleep_fn
        self._playwright = None
        self._browser = None

    def __enter__(self) -> PlaywrightRenderer:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - depends on the extra
            raise RendererUnavailableError(
                "--dynamic needs Playwright: pip install '.[dynamic]' "
                "&& playwright install chromium"
            ) from exc

        self._playwright = sync_playwright().start()
        try:
            self._browser = self._playwright.chromium.launch(headless=True)
        except Exception as exc:  # pragma: no cover - depends on the browser install
            self._playwright.stop()
            self._playwright = None
            raise RendererUnavailableError(
                f"Playwright is installed but its browser could not start ({exc}). "
                "Run: playwright install chromium"
            ) from exc
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None

    def render(self, url: str, *, expand: bool | None = None) -> str:
        """The page's HTML after scripts have run — and, with `expand`, after
        its A-Z tabs and "load more" controls have been clicked.

        Returns every snapshot concatenated, not just the last one: clicking a
        letter tab usually *replaces* the visible list, so the last snapshot
        alone would lose the people who were on screen before. The caller only
        reads `<a href>` out of this and dedupes by normalized URL, so a
        concatenation is exactly the union it needs.

        Raises on failure, which `stages/crawl.py` treats as "no better than
        the static HTML".
        """
        if self._browser is None:
            raise RendererUnavailableError("renderer used outside its context manager")
        if self._delay:
            self._sleep(self._delay)

        context = self._browser.new_context(user_agent=self._user_agent)
        try:
            page = context.new_page()
            page.goto(url, timeout=self._timeout_ms, wait_until=self._wait_until)
            page.wait_for_timeout(self._settle_ms)
            snapshots = [page.content()]
            if self._expand if expand is None else expand:
                snapshots.extend(self._expanded_snapshots(page, url))
        finally:
            context.close()

        html = "\n".join(snapshots)
        self._logger.info(
            "rendered %s (%d snapshot(s), %d bytes)", url, len(snapshots), len(html)
        )
        return html

    def _expanded_snapshots(self, page, url: str) -> list[str]:
        """Click the controls that reveal the rest of a directory, keeping a
        snapshot after each one.

        Bard's faculty page is the case this exists for: it server-renders 19
        people whose surnames all begin with A, and the other 28 letters are
        `<a href="#b">`-style tabs that swap the list by script. Rendering
        alone changes nothing there — the page looks identical — so the
        fallback has to press the tabs.

        One snapshot *per* click, not one at the end: these controls replace
        the list rather than extend it, so a single final snapshot would hold
        only the last letter. Playwright's own `click()` waits for
        actionability and times out on Bard's tabs (they sit under an
        overlay); a DOM-dispatched click is what the page's handler listens
        for.
        """
        snapshots: list[str] = []
        try:
            controls = page.evaluate(_COUNT_EXPANDERS_JS)
        except Exception as exc:  # noqa: BLE001 - expansion is best-effort
            self._logger.info("expansion skipped on %s (%s)", url, exc)
            return snapshots

        for index in range(min(controls, self._max_expansions)):
            try:
                page.evaluate(_CLICK_EXPANDER_JS, index)
                page.wait_for_timeout(self._click_settle_ms)
                snapshots.append(page.content())
            except Exception as exc:  # noqa: BLE001 - one bad control is not fatal
                self._logger.info("expander %d failed on %s (%s)", index, url, exc)

        if snapshots:
            self._logger.info(
                "clicked %d expander control(s) on %s", len(snapshots), url
            )
        return snapshots


# The two halves of the expansion pass, kept as one definition of "an expander"
# so counting and clicking cannot drift apart.
_EXPANDER_QUERY_JS = """
    const isLetterTab = (el) =>
        (el.getAttribute('href') || '').startsWith('#') &&
        /^[A-Za-z]$/.test((el.textContent || '').trim());
    const isLoadMore = (el) =>
        /\b(load|show|view)\s+(more|all)\b/i.test((el.textContent || '').trim());
    const controls = Array.from(
        document.querySelectorAll('a[href^="#"], button')
    ).filter((el) => isLetterTab(el) || isLoadMore(el));
"""

_COUNT_EXPANDERS_JS = "() => {" + _EXPANDER_QUERY_JS + " return controls.length; }"

_CLICK_EXPANDER_JS = (
    "(index) => {"
    + _EXPANDER_QUERY_JS
    + " const el = controls[index]; if (el) { el.click(); return true; } return false; }"
)
