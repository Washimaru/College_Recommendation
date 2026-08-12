"""The headless-render fallback, exercised against a real browser.

Skipped when Playwright or its browser isn't installed — it is an optional
extra (`.[dynamic]`), and the rest of the pipeline must test without it.
The fixture reproduces the shape that made this necessary: a directory that
server-renders one letter and swaps in the rest when a tab is clicked.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from faculty_pipeline.services.dynamic import PlaywrightRenderer, RendererUnavailableError

FIXTURE = Path(__file__).parent / "fixtures" / "dynamic" / "az_directory.html"


@pytest.fixture(scope="module")
def renderer():
    try:
        with PlaywrightRenderer(user_agent="pytest", settle_ms=200) as r:
            yield r
    except RendererUnavailableError as exc:
        pytest.skip(f"playwright unavailable: {exc}")


def _render(renderer) -> str:
    return renderer.render(FIXTURE.as_uri())


def _link(slug: str) -> str:
    return f'href="/faculty/{slug}"' 


class TestPlaywrightRenderer:
    def test_returns_the_served_html(self, renderer):
        html = _render(renderer)

        assert _link("adams-ann") in html

    def test_clicking_the_letter_tabs_reveals_the_rest(self, renderer):
        html = _render(renderer)

        assert _link("brown-bea") in html
        assert _link("chen-cy") in html

    def test_the_first_letter_survives_being_replaced(self, renderer):
        """Each click overwrites the list, so only keeping the final snapshot
        would silently lose everyone shown before it."""
        html = _render(renderer)

        assert _link("adams-ann") in html and _link("cruz-caz") in html

    def test_expansion_can_be_turned_off(self, renderer):
        """Per call, not per instance: Playwright refuses to start twice in
        one process, so behaviour that varies has to be an argument."""
        html = renderer.render(FIXTURE.as_uri(), expand=False)

        assert _link("adams-ann") in html
        # The slug appears in the page's inline script either way, so the
        # assertion is on the anchor the crawler would actually read.
        assert _link("brown-bea") not in html

    def test_using_it_outside_its_context_manager_is_an_error(self):
        renderer = PlaywrightRenderer(user_agent="pytest")

        with pytest.raises(RendererUnavailableError):
            renderer.render("https://example.com")
