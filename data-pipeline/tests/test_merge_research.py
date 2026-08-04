"""The merge is the gate between web research and the shipped catalog.

Its job is to refuse things: unsourced claims about named people, hedged
non-findings dressed as findings, and later passes quietly overwriting
hand-checked data.
"""
from __future__ import annotations

from merge_research import clean_entry, is_empty, merge

SRC = ["https://www.example.edu/faculty"]


class TestIsEmpty:
    def test_recognises_the_ways_research_says_nothing(self):
        for value in ("", "  ", "N/A", "none found", "Unknown", "TBD", None):
            assert is_empty(value), value

    def test_real_content_is_not_empty(self):
        assert not is_empty("Prof. Jane Doe, 2024 Turing Award")

    def test_a_dict_of_nothings_is_empty(self):
        assert is_empty({"level": "", "areas": "N/A"})

    def test_a_dict_with_one_real_value_is_not(self):
        assert not is_empty({"level": "", "areas": "Quantum computing"})


class TestCleanEntry:
    def test_keeps_a_sourced_finding(self):
        entry = clean_entry({"faculty": "Prof. Jane Doe (Turing 2024)", "src": SRC})

        assert entry is not None
        assert entry["faculty"].startswith("Prof. Jane Doe")
        assert entry["src"] == SRC

    def test_drops_an_unsourced_claim_about_a_person(self):
        """A named professor without a URL is unverifiable, however plausible."""
        assert clean_entry({"faculty": "Prof. Jane Doe, Nobel laureate"}) is None

    def test_drops_a_non_finding_even_when_sourced(self):
        assert clean_entry({"faculty": "none found", "src": SRC}) is None

    def test_drops_a_non_http_source(self):
        assert clean_entry({"faculty": "Prof. Jane Doe", "src": ["I recall this"]}) is None

    def test_keeps_research_without_faculty(self):
        entry = clean_entry({"research": {"areas": "Robotics"}, "src": SRC})

        assert entry is not None and "faculty" not in entry


class TestMerge:
    def test_adds_to_a_school_with_no_details(self):
        details: dict = {}
        merged, stats = merge(details, {"mit": {"faculty": "Prof. A", "src": SRC}})

        assert merged["mit"]["faculty"] == "Prof. A"
        assert stats["new_schools"] == 1

    def test_never_overwrites_an_existing_section(self):
        """Re-running a batch must not replace hand-checked data."""
        details = {"mit": {"faculty": "hand-checked", "src": ["https://a.edu"]}}
        merged, stats = merge(details, {"mit": {"faculty": "later weaker pass", "src": SRC}})

        assert merged["mit"]["faculty"] == "hand-checked"
        assert stats["skipped_existing"] == 1

    def test_fills_only_the_missing_section(self):
        details = {"mit": {"faculty": "hand-checked", "src": ["https://a.edu"]}}
        merged, _ = merge(
            details, {"mit": {"faculty": "ignored", "research": {"areas": "AI"}, "src": SRC}}
        )

        assert merged["mit"]["faculty"] == "hand-checked"
        assert merged["mit"]["research"] == {"areas": "AI"}

    def test_preserves_unrelated_sections(self):
        details = {"mit": {"scholarships": {"policy": "need-blind"}, "src": ["https://a.edu"]}}
        merged, _ = merge(details, {"mit": {"faculty": "Prof. A", "src": SRC}})

        assert merged["mit"]["scholarships"] == {"policy": "need-blind"}

    def test_unions_sources_without_duplicating(self):
        details = {"mit": {"src": ["https://a.edu"]}}
        merged, _ = merge(details, {"mit": {"faculty": "Prof. A", "src": ["https://a.edu", *SRC]}})

        assert merged["mit"]["src"] == ["https://a.edu", *SRC]

    def test_a_school_with_nothing_verifiable_gets_no_section(self):
        details: dict = {}
        merged, stats = merge(details, {"nowhere": {"faculty": "not found"}})

        assert "nowhere" not in merged
        assert stats["skipped_empty"] == 1
