"""Stage: active faculty.

Every guard here was written against something that actually happened when
this source was measured, and the tests name the case rather than the rule.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from faculty_pipeline.config import Config
from faculty_pipeline.models import School
from faculty_pipeline.services.checkpoint import CheckpointStore
from faculty_pipeline.services.openalex import normalize_homepage
from faculty_pipeline.stages import active_faculty
from faculty_pipeline.stages.active_faculty import match_name, plausible_here

logger = logging.getLogger("test")


def _config(tmp_path: Path, **overrides: object) -> Config:
    return Config(
        input_path=tmp_path / "schools.json",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        checkpoint_dir=tmp_path / "checkpoints",
        log_dir=tmp_path / "logs",
        output_dir=tmp_path / "output",
        **overrides,
    )


def _school(school_id="acme-college", name="Acme College", homepage="https://www.acme.edu"):
    return School(school_id=school_id, name=name, slug=school_id, country="US", homepage=homepage)


def _write_schools(config: Config, schools: list[School]) -> None:
    path = Path(config.data_dir) / "schools.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(s.model_dump_json() for s in schools) + "\n", encoding="utf-8")


def _checkpoint(config: Config) -> CheckpointStore:
    return CheckpointStore(Path(config.checkpoint_dir) / "active-faculty.json")


def _author(aid: str, name: str, topics: list[tuple[str, str]], last_year: int = 2026) -> dict:
    return {
        "id": f"https://openalex.org/{aid}",
        "display_name": name,
        "topics": [
            {"display_name": topic, "field": {"display_name": fld}} for topic, fld in topics
        ],
        "counts_by_year": [{"year": last_year, "works_count": 3}],
    }


@dataclass
class FakeApi:
    institution: dict | None = None
    counts: list[tuple[str, str, int]] = field(default_factory=list)
    author_records: dict[str, dict] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def institution_for(self, name: str, homepage: str | None) -> dict | None:
        self.calls.append(f"institution:{name}")
        return self.institution

    def recent_author_counts(self, institution_id: str, since_year: int, *, limit: int = 60):
        self.calls.append(f"works:{institution_id}:{since_year}")
        return list(self.counts)

    def authors(self, author_ids: list[str]) -> dict[str, dict]:
        return {a: self.author_records[a] for a in author_ids if a in self.author_records}


def _run(config: Config, api: FakeApi, **kwargs):
    return active_faculty.run(config, _checkpoint(config), logger, api, **kwargs)


def _records(config: Config) -> list[dict]:
    path = Path(config.data_dir) / "active_faculty.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


INSTITUTION = {"id": "https://openalex.org/I999", "display_name": "Acme College",
               "homepage_url": "https://www.acme.edu"}


class TestTheAstronomersAtTheMusicCollege:
    """OpenAlex files 80 JWST papers under Berklee College of Music. A student
    reading a music school's page must not meet gravitational lensing."""

    def test_research_that_matches_nothing_the_school_teaches_is_dropped(self, tmp_path: Path):
        config = _config(tmp_path)
        _write_schools(config, [_school()])
        api = FakeApi(
            institution=INSTITUTION,
            counts=[("A1", "Adi Zitrin", 9), ("A2", "Real Musician", 4)],
            author_records={
                "A1": _author("A1", "Adi Zitrin",
                              [("Galaxies: Formation", "Physics and Astronomy")]),
                "A2": _author("A2", "Real Musician", [("Music Education", "Arts and Humanities")]),
            },
        )

        summary = _run(config, api, programs_by_school={
            "acme-college": {"Visual & Performing Arts"},
        })

        assert [p["name"] for p in _records(config)[0]["active_faculty"]] == ["Real Musician"]
        assert any("match nothing the school awards" in note for note in summary.notes)

    def test_a_school_with_no_degree_data_rejects_nobody(self, tmp_path: Path):
        """An absent catalog fact is not evidence against a person."""
        config = _config(tmp_path)
        _write_schools(config, [_school()])
        api = FakeApi(
            institution=INSTITUTION, counts=[("A1", "Someone", 5)],
            author_records={"A1": _author("A1", "Someone", [("X", "Physics and Astronomy")])},
        )

        _run(config, api, programs_by_school={})

        assert len(_records(config)[0]["active_faculty"]) == 1

    def test_plausibility_accepts_a_related_family(self):
        assert plausible_here(["Mathematics"], {"Computer & Information Sciences"})
        assert plausible_here(["Economics, Econometrics and Finance"], {"Social Sciences"})

    def test_an_incidental_second_field_does_not_wave_someone_through(self):
        """The hole this closed: four JWST astronomers reached Berklee's page
        because one of their topics touched Computer Science, which a music
        college does award. Their primary field is what they do."""
        astronomer = ["Physics and Astronomy", "Computer Science"]

        assert not plausible_here(astronomer, {"Computer & Information Sciences",
                                               "Visual & Performing Arts"})

    def test_plausibility_rejects_an_unrelated_one(self):
        assert not plausible_here(["Physics and Astronomy"], {"Visual & Performing Arts"})

    def test_an_author_with_no_fields_at_all_is_not_waved_through(self):
        assert not plausible_here([], {"Visual & Performing Arts"})


class TestWhatEachRecordSays:
    def _one(self, tmp_path: Path, author: dict, works: int = 8) -> dict:
        config = _config(tmp_path)
        _write_schools(config, [_school()])
        api = FakeApi(
            institution=INSTITUTION,
            counts=[(author["id"].rsplit("/", 1)[-1], author["display_name"], works)],
            author_records={author["id"].rsplit("/", 1)[-1]: author},
        )
        _run(config, api)
        return _records(config)[0]["active_faculty"][0]

    def test_it_says_what_they_research_not_what_they_are(self, tmp_path: Path):
        """"Mathematical Dynamics and Fractals" is the point; "mathematician"
        is what the Wikipedia-sourced list already gives."""
        person = self._one(tmp_path, _author("A1", "Jim Wiseman", [
            ("Mathematical Dynamics and Fractals", "Mathematics"),
            ("Advanced Topology and Set Theory", "Mathematics"),
        ]))

        assert person["research"][:2] == [
            "Mathematical Dynamics and Fractals", "Advanced Topology and Set Theory",
        ]

    def test_it_records_how_recently_they_published(self, tmp_path: Path):
        person = self._one(tmp_path, _author("A1", "Jim Wiseman",
                                             [("X", "Mathematics")], last_year=2026))

        assert person["last_active"] == 2026
        assert person["recent_works"] == 8

    def test_it_links_to_the_source(self, tmp_path: Path):
        person = self._one(tmp_path, _author("A1", "Jim Wiseman", [("X", "Mathematics")]))

        assert person["source"] == "openalex"
        assert person["source_url"].endswith("/A1")

    def test_no_contact_details_are_carried(self, tmp_path: Path):
        person = self._one(tmp_path, _author("A1", "Jim Wiseman", [("X", "Mathematics")]))

        assert set(person) == {
            "name", "research", "fields", "recent_works", "last_active",
            "h_index", "awards", "source", "source_url",
        }


class TestInstitutionResolution:
    def test_an_unconfirmed_school_yields_nobody_rather_than_a_guess(self, tmp_path: Path):
        """A bare name search for "Berklee" once returned Google (Canada);
        a wrong institution produces a page of confidently wrong people."""
        config = _config(tmp_path)
        _write_schools(config, [_school()])
        api = FakeApi(institution=None, counts=[("A1", "Nobody", 5)])

        summary = _run(config, api)

        assert _records(config)[0]["active_faculty"] == []
        assert any("no confirmable OpenAlex institution" in note for note in summary.notes)

    def test_homepages_compare_regardless_of_scheme_or_www(self):
        assert normalize_homepage("web.mit.edu/") == normalize_homepage("https://web.mit.edu")
        assert normalize_homepage("https://www.acme.edu") == normalize_homepage("acme.edu")
        assert normalize_homepage(None) is None

    def test_different_schools_do_not_compare_equal(self):
        assert normalize_homepage("https://www.berklee.edu") != normalize_homepage(
            "https://www.google.ca"
        )


class TestRunMechanics:
    def test_the_list_is_capped(self, tmp_path: Path):
        config = _config(tmp_path)
        _write_schools(config, [_school()])
        counts = [(f"A{i}", f"Person {i}", 10 - i % 5) for i in range(30)]
        api = FakeApi(
            institution=INSTITUTION, counts=counts,
            author_records={a: _author(a, n, [("X", "Mathematics")]) for a, n, _ in counts},
        )

        _run(config, api, per_school=20)

        assert len(_records(config)[0]["active_faculty"]) == 20

    def test_a_done_school_is_not_looked_up_again(self, tmp_path: Path):
        config = _config(tmp_path)
        _write_schools(config, [_school()])
        api = FakeApi(institution=INSTITUTION)

        _run(config, api)
        _run(config, api)

        assert sum(1 for c in api.calls if c.startswith("institution:")) == 1

    def test_a_failure_is_retried_next_run(self, tmp_path: Path):
        config = _config(tmp_path)
        _write_schools(config, [_school()])

        class Boom(FakeApi):
            def institution_for(self, name, homepage):
                raise RuntimeError("openalex down")

        summary = _run(config, Boom())

        assert summary.failed == 1
        assert not _checkpoint(config).is_done("acme-college")

    def test_non_us_schools_are_skipped(self, tmp_path: Path):
        config = _config(tmp_path)
        _write_schools(config, [School(school_id="ox", name="Oxford", slug="ox",
                                       country="UK", homepage="https://ox.ac.uk")])
        api = FakeApi(institution=INSTITUTION)

        _run(config, api)

        assert api.calls == []

    def test_dry_run_makes_no_requests(self, tmp_path: Path):
        config = _config(tmp_path)
        _write_schools(config, [_school()])
        api = FakeApi(institution=INSTITUTION)

        summary = _run(config, api, dry_run=True)

        assert api.calls == []
        assert any("dry-run" in note for note in summary.notes)

    def test_the_tier_file_needs_a_run_first(self, tmp_path: Path):
        config = _config(tmp_path)

        with pytest.raises(active_faculty.ActiveFacultyError, match="Run `active-faculty` first"):
            active_faculty.write_tier_file(config.data_dir, tmp_path / "tier.json")


class TestThePolitePool:
    """OpenAlex gives 100,000 requests a day to callers who identify
    themselves and 1,000 to those who don't. The first full run stopped after
    63 schools on a quota 429 because the pipeline's stock User-Agent carries
    no address OpenAlex recognises. `mailto` is how you ask for the polite
    pool, and it is a courtesy as much as a quota.
    """

    @dataclass
    class RecordingHttp:
        urls: list[str] = field(default_factory=list)

        def fetch(self, url: str, *, method: str = "GET"):
            self.urls.append(url)

            @dataclass
            class R:
                body: str = '{"results": []}'

            return R()

    def test_the_address_stays_out_of_the_url(self):
        """Rewritten: this case used to assert `mailto=` was *in* every URL.

        That was the original design and it was wrong. The HTTP cache is keyed
        on the URL, so putting the address there changed every key and threw
        away 63 schools' worth of already-fetched responses — spending quota to
        re-buy what was on disk, in the name of raising the quota. The address
        now travels in the User-Agent (OpenAlex documents both), and what this
        case guards is that it never comes back to the URL.
        """
        from faculty_pipeline.services.openalex import OpenAlexApi

        http = self.RecordingHttp()
        api = OpenAlexApi(http, mailto="someone@example.edu")

        api.get("institutions", search="Acme")
        api.get("authors", filter="openalex_id:A1")

        assert http.urls, "no request was made"
        assert not any("mailto" in u for u in http.urls), http.urls

    def test_the_url_is_the_same_with_or_without_an_address(self):
        """The cache-key property stated directly."""
        from faculty_pipeline.services.openalex import OpenAlexApi

        with_addr, without = self.RecordingHttp(), self.RecordingHttp()
        OpenAlexApi(with_addr, mailto="someone@example.edu").get("authors", search="x")
        OpenAlexApi(without, mailto=None).get("authors", search="x")

        assert with_addr.urls == without.urls

    def test_without_an_address_it_still_works(self):
        """A missing address costs quota, not correctness — the stage must not
        refuse to run because nobody set one."""
        from faculty_pipeline.services.openalex import OpenAlexApi

        http = self.RecordingHttp()
        OpenAlexApi(http).get("institutions", search="Acme")

        assert http.urls and "mailto" not in http.urls[0]


class TestPriority:
    """Who leads the list.

    The rule, in order: someone recognised for their research, then someone
    whose work is widely built on, then someone simply publishing a lot from
    here. Awards come from Wikidata via the notable list — ORCID records them
    in principle and not in practice (0 of 12 highly-cited MIT researchers had
    one). h-index is OpenAlex's, and arrives in the request the stage already
    makes.
    """

    def _api(self, people: list[tuple[str, str, int, int]]) -> FakeApi:
        counts = [(f"A{i}", name, works) for i, (name, _, works, _) in enumerate(people)]
        records = {}
        for i, (name, _, _, h) in enumerate(people):
            author = _author(f"A{i}", name, [("Topic", "Mathematics")])
            author["summary_stats"] = {"h_index": h}
            records[f"A{i}"] = author
        return FakeApi(institution=INSTITUTION, counts=counts, author_records=records)

    def _run_with(self, tmp_path: Path, api: FakeApi, honours=None) -> list[dict]:
        """Honours are keyed through `match_name`, exactly as the CLI keys them
        when it loads the notable tier file. Keying by raw name here would let
        a lookup-key mismatch pass the tests and fail on real data."""
        config = _config(tmp_path)
        _write_schools(config, [_school()])
        keyed = {match_name(name): awards for name, awards in (honours or {}).items()}
        _run(config, api, honours_by_school={"acme-college": keyed})
        return _records(config)[0]["active_faculty"]

    def test_an_award_winner_leads_a_more_prolific_colleague(self, tmp_path: Path):
        api = self._api([("Prolific Pat", "", 20, 10), ("Laureate Lee", "", 3, 8)])

        people = self._run_with(tmp_path, api, {"Laureate Lee": ["Fields Medal"]})

        assert [p["name"] for p in people] == ["Laureate Lee", "Prolific Pat"]
        assert people[0]["awards"] == ["Fields Medal"]

    def test_impact_breaks_the_tie_when_nobody_has_an_award(self, tmp_path: Path):
        api = self._api([("Low Impact", "", 20, 4), ("High Impact", "", 5, 40)])

        people = self._run_with(tmp_path, api)

        assert [p["name"] for p in people] == ["High Impact", "Low Impact"]

    def test_output_breaks_the_tie_when_impact_matches(self, tmp_path: Path):
        api = self._api([("Fewer Papers", "", 2, 10), ("More Papers", "", 9, 10)])

        people = self._run_with(tmp_path, api)

        assert [p["name"] for p in people] == ["More Papers", "Fewer Papers"]

    def test_the_h_index_is_carried_so_the_ranking_can_be_explained(self, tmp_path: Path):
        api = self._api([("Someone", "", 5, 27)])

        people = self._run_with(tmp_path, api)

        assert people[0]["h_index"] == 27

    def test_no_awards_means_an_empty_list_not_a_missing_key(self, tmp_path: Path):
        api = self._api([("Someone", "", 5, 3)])

        assert self._run_with(tmp_path, api)[0]["awards"] == []


class TestAwardMatchingToleratesNameSpelling:
    """The two lists spell people differently: Wikipedia disambiguates with
    "(American writer)" and keeps diacritics, OpenAlex does neither. Exact
    matching is why "Mary McCarthy" and "Rosemary Lévy Zumwalt" missed.

    Worth stating plainly: this recovers a handful of people, not hundreds.
    Only 10 names are shared between the 2,366 award-holders and the 3,165
    active researchers, because Wikipedia's faculty categories and OpenAlex's
    recent publishers are largely different populations. The ranking rests on
    the h-index, which 99.7% of these researchers have.
    """

    def test_a_disambiguator_does_not_block_the_match(self):
        from faculty_pipeline.stages.active_faculty import match_name

        assert match_name("Mary McCarthy (American writer)") == match_name("Mary McCarthy")

    def test_diacritics_do_not_block_the_match(self):
        from faculty_pipeline.stages.active_faculty import match_name

        assert match_name("Rosemary Lévy Zumwalt") == match_name("Rosemary Levy Zumwalt")

    def test_two_different_people_still_differ(self):
        from faculty_pipeline.stages.active_faculty import match_name

        assert match_name("John Smith") != match_name("Jane Smith")


class TestHyperauthorshipDoesNotPutStrangersOnAPage:
    """A CMS/ATLAS paper carries thousands of authors and lists every
    participating institution, so "wrote a paper from MIT" made MIT's top
    three M. Tytgat (Ghent), R. Klanner (DESY) and Y. Yang — particle
    physicists with h-indexes near 150 who mostly do not work there.

    The author's own affiliation record settles it, and arrives in the
    request the stage already makes. Measured on MIT: of 50 candidates, 6
    claim MIT recently and 44 do not.

    The cost is shorter lists, and that is the right trade. A student reading
    a school's page should not be shown someone who works somewhere else.
    """

    def test_someone_who_never_claims_the_school_is_dropped(self):
        from faculty_pipeline.stages.active_faculty import affiliated_recently

        author = {"affiliations": [
            {"institution": {"id": "https://openalex.org/I999"}, "years": [2025, 2024]},
        ]}

        assert not affiliated_recently(author, "I63966007", 2023)

    def test_a_current_affiliation_is_kept(self):
        from faculty_pipeline.stages.active_faculty import affiliated_recently

        author = {"affiliations": [
            {"institution": {"id": "https://openalex.org/I63966007"}, "years": [2025, 2024]},
        ]}

        assert affiliated_recently(author, "I63966007", 2023)

    def test_an_old_affiliation_is_not_enough(self):
        """Yoshua Bengio was an MIT postdoc in 1991. That is not faculty now."""
        from faculty_pipeline.stages.active_faculty import affiliated_recently

        author = {"affiliations": [
            {"institution": {"id": "https://openalex.org/I63966007"}, "years": [1991, 1992]},
        ]}

        assert not affiliated_recently(author, "I63966007", 2023)

    def test_no_affiliation_data_is_not_evidence_against(self):
        """An author record with no affiliations at all is unmeasured, not a
        denial — the same honest-null rule the catalog uses everywhere."""
        from faculty_pipeline.stages.active_faculty import affiliated_recently

        assert affiliated_recently({"affiliations": []}, "I63966007", 2023)
