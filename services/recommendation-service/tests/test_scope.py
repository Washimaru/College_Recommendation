"""Country scope filters candidates before ranking.

Applied at candidate selection, not by hiding results afterwards: hiding would
mean a student asking for 10 US schools gets fewer than 10.
"""
from __future__ import annotations

from app.candidates import in_scope
from app.schemas import Culture, University

NEUTRAL = Culture(collab=0.5, quirky=0.5, idealist=0.5, research=0.5, spirit=0.5, seminar=0.5)


def _uni(country: str) -> University:
    return University(
        id=country.lower(), name=f"U {country}", country=country, location="x",
        region="International", setting="urban", type="Public",
        avg_gpa=3.5, size="medium", majors=["CS"], culture=NEUTRAL,
    )


CATALOG = [_uni("USA"), _uni("UK"), _uni("Japan")]


def test_both_keeps_everything():
    assert len(in_scope(CATALOG, "both")) == 3


def test_usa_keeps_only_us_schools():
    assert [u.country for u in in_scope(CATALOG, "usa")] == ["USA"]


def test_international_excludes_us_schools():
    assert sorted(u.country for u in in_scope(CATALOG, "international")) == ["Japan", "UK"]


def test_unknown_scope_falls_back_to_everything():
    """A scope we do not recognise must not silently empty the catalog."""
    assert len(in_scope(CATALOG, "nonsense")) == 3
