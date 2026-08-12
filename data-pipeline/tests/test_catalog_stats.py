"""The counts the UI quotes are generated, not typed in.

`out/universities.json` is a build artifact regenerated from the committed
sources, so any rebuild that changes the catalog size used to falsify "358
universities" on every page of the site - the number was typed into five
frontend files by hand, and `364` had already survived elsewhere. The catalog
build now emits the numbers the UI quotes, and the UI reads them.
"""
from __future__ import annotations

from build_catalog import catalog_stats, render_stats_module

CATALOG = [
    {"id": "a", "country": "USA", "setting": "rural", "details": {"research": {"level": "R1"}}},
    {"id": "b", "country": "USA", "setting": "urban", "details": None},
    {"id": "c", "country": "UK", "setting": "urban"},
]


class TestCatalogStats:
    def test_counts_every_school(self):
        assert catalog_stats(CATALOG)["size"] == 3

    def test_counts_rural_schools(self):
        """The rural count is quoted to justify treating setting as soft."""
        assert catalog_stats(CATALOG)["rural"] == 1

    def test_counts_schools_with_a_curated_profile(self):
        assert catalog_stats(CATALOG)["with_details"] == 1

    def test_an_empty_details_object_is_not_a_profile(self):
        assert catalog_stats([{"id": "a", "country": "USA", "details": {}}])["with_details"] == 0


class TestRenderStatsModule:
    def test_exports_each_count_as_a_constant(self):
        module = render_stats_module({"size": 358, "rural": 28, "with_details": 276})

        assert "export const CATALOG_SIZE = 358;" in module
        assert "export const RURAL_COUNT = 28;" in module
        assert "export const WITH_DETAILS_COUNT = 276;" in module

    def test_says_it_is_generated(self):
        """Anyone who opens it to hand-edit a number should be stopped there."""
        module = render_stats_module({"size": 1, "rural": 0, "with_details": 0})

        assert "generated" in module.lower()
        assert "build_catalog.py" in module

    def test_ends_with_a_newline(self):
        module = render_stats_module({"size": 1, "rural": 0, "with_details": 0})

        assert module.endswith("\n")
