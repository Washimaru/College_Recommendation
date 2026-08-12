"""Faculty vs staff.

The first live extract run put ArtCenter's "Senior Vice President of
Advancement", "Executive Vice President Operations and Finance" and "Vice
President of Student Affairs" into master.csv as professors. Nothing was
wrong with the extraction — they are real named people with real titles on
real pages — but nobody had asked whether they teach. ArtCenter's sitemap
cluster mixes staff into `/people/`, so the crawler cannot avoid them; the
distinction has to be made from the title.

Deliberately conservative: only a *clear* administrative title with no
academic rank in it is called staff. Anything unrecognised is `None`
(unknown) and is kept, because dropping a real professor is worse than
keeping an unclassifiable row that the CSV labels honestly.
"""
from __future__ import annotations

import pytest

from faculty_pipeline.utils import classify_role


class TestAcademicTitlesAreFaculty:
    @pytest.mark.parametrize(
        "title",
        [
            "Associate Professor of Business Management",
            "Assistant Professor of Medical Sciences",
            "Professor",
            "Professor Emerita of Chemistry",
            "Visiting Assistant Professor",
            "Adjunct Instructor, Painting",
            "Senior Lecturer in Mathematics",
            "Artist in Residence",
            "Clinical Professor of Nursing",
            "Postdoctoral Fellow in Physics",
        ],
    )
    def test_academic_rank_is_faculty(self, title: str):
        assert classify_role(title) is True

    def test_an_academic_rank_wins_over_an_administrative_one(self):
        """Plenty of real professors also hold an administrative post; the
        teaching appointment is the one that decides."""
        assert classify_role("Dean of the Faculty and Professor of Biology") is True
        assert classify_role("Provost and Professor of History") is True
        assert classify_role("Department Chair and Associate Professor of Art") is True


class TestAdministrativeTitlesAreStaff:
    @pytest.mark.parametrize(
        "title",
        [
            "Senior Vice President of Advancement",
            "Executive Vice President Operations and Finance, Penske Media Corporation",
            "Vice President of Student Affairs",
            "Chief Financial Officer",
            "Registrar",
            "Director of Admissions",
            "Director of Human Resources",
            "Head Coach, Women's Basketball",
            "Administrative Assistant",
        ],
    )
    def test_clear_administrative_titles_are_not_faculty(self, title: str):
        assert classify_role(title) is False


class TestTitlesFromTheLiveArtCenterRun:
    """Real titles from the first live run. ArtCenter publishes trustees,
    alumni and corporate advisers in the same `/people/` tree as its faculty,
    so these are what the crawler actually brings back."""

    @pytest.mark.parametrize(
        "title",
        [
            "Philanthropist; ArtCenter Trustee Emeritus",
            "Member, Board of Trustees",
            "Chief Designer, Tesla",
            "Founder, JANUS et Cie",
            "Alumnus (BFA 93); Artist, Entrepreneur, and Educational Innovator",
            "Board Chair; CEO and Chief Creative Officer, Su Mathews Hale Design",
            "Former Design Principal, AC Martin Partners",
        ],
    )
    def test_trustees_alumni_and_corporate_advisers_are_not_faculty(self, title: str):
        assert classify_role(title) is False

    def test_emeritus_alone_does_not_make_someone_a_professor(self):
        """"Trustee Emeritus" is an honour, not an appointment — the earlier
        version of this classifier read the word and called it faculty."""
        assert classify_role("Trustee Emeritus") is False
        assert classify_role("Professor Emeritus of Design") is True
        assert classify_role("Emeritus Faculty") is True

    def test_a_teaching_title_still_wins(self):
        assert classify_role("Instructor") is True
        assert classify_role("Department Chair, Undergraduate Illustration") is None


class TestUnknownStaysUnknown:
    @pytest.mark.parametrize("title", [None, "", "   ", "Fellow", "Staff", "Curator"])
    def test_anything_unrecognised_is_unknown(self, title: str | None):
        assert classify_role(title) is None

    def test_a_generic_director_is_not_assumed_to_be_staff(self):
        """"Director of Undergraduate Studies" is usually a professor; only
        the named administrative directorships are treated as staff."""
        assert classify_role("Director of the Writing Center") is None
