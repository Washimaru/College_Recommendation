"""Stage: notable faculty.

The failure this stage exists to make impossible is a professor who does not
exist. Every test below is ultimately about that: a page that is not a person
is dropped, a school with nobody gets an empty list rather than a padded one,
and nothing is ever synthesised to reach a target count.
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
from faculty_pipeline.services.wikimedia import ApiRobots, MediaWikiApi
from faculty_pipeline.stages import notable

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


def _school(school_id: str = "acme-college", name: str = "Acme College") -> School:
    return School(
        school_id=school_id, name=name, slug=school_id, country="US",
        homepage="https://www.acme.edu",
    )


def _write_schools(config: Config, schools: list[School]) -> None:
    path = Path(config.data_dir) / "schools.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(s.model_dump_json() for s in schools) + "\n", encoding="utf-8")


def _checkpoint(config: Config) -> CheckpointStore:
    return CheckpointStore(Path(config.checkpoint_dir) / "notable.json")


def _person(qid: str, langs: int, *, dead: bool = False, desc: str = "American physicist",
            occupations: list[str] | None = None) -> dict:
    claims: dict = {"P31": [{"mainsnak": {"datavalue": {"value": {"id": "Q5"}}}}]}
    if dead:
        claims["P570"] = [{"mainsnak": {"datavalue": {"value": {"time": "+1984-04-22T00:00:00Z"}}}}]
    if occupations:
        claims["P106"] = [
            {"mainsnak": {"datavalue": {"value": {"id": q}}}} for q in occupations
        ]
    return {
        "id": qid,
        "claims": claims,
        "descriptions": {"en": {"value": desc}},
        "sitelinks": {f"lang{i}wiki": {} for i in range(langs)},
    }


@dataclass
class FakeApi:
    """Stands in for the two live APIs; every test states its own world."""

    members: dict[str, list[str]] = field(default_factory=dict)
    qids: dict[str, str] = field(default_factory=dict)
    ents: dict[str, dict] = field(default_factory=dict)
    label_map: dict[str, str] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def category_members(self, category: str, *, cap: int = 1500) -> list[str]:
        self.calls.append(category)
        return list(self.members.get(category, []))

    def wikidata_ids(self, titles: list[str]) -> dict[str, str]:
        return {t: self.qids[t] for t in titles if t in self.qids}

    def entities(self, qids: list[str]) -> dict[str, dict]:
        return {q: self.ents[q] for q in qids if q in self.ents}

    def labels(self, qids: list[str]) -> dict[str, str]:
        return {q: self.label_map[q] for q in qids if q in self.label_map}

    # The resolution fallbacks. A plain fake school resolves on its first try,
    # so these answer "nothing found" unless a test says otherwise.
    def canonical_title(self, name: str) -> str | None:
        return None

    def search_article(self, name: str) -> str | None:
        return None

    def search_faculty_category(self, name: str) -> str | None:
        return None


def _run(config: Config, api: FakeApi, **kwargs):
    return notable.run(config, _checkpoint(config), logger, api, **kwargs)


def _records(config: Config) -> list[dict]:
    path = Path(config.data_dir) / "notable_faculty.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class TestNobodyIsInvented:
    def test_a_page_that_is_not_a_person_is_dropped(self, tmp_path: Path):
        config = _config(tmp_path)
        _write_schools(config, [_school()])
        api = FakeApi(
            members={"Category:Acme College faculty": ["Jane Doe", "Acme Physics Laboratory"]},
            qids={"Jane Doe": "Q1", "Acme Physics Laboratory": "Q2"},
            ents={
                "Q1": _person("Q1", 12),
                # A research centre: a real Wikidata item, not a human.
                "Q2": {"id": "Q2", "claims": {"P31": [
                    {"mainsnak": {"datavalue": {"value": {"id": "Q31855"}}}}]}},
            },
        )

        _run(config, api)

        names = [p["name"] for p in _records(config)[0]["notable_faculty"]]
        assert names == ["Jane Doe"]

    def test_list_articles_never_become_professors(self, tmp_path: Path):
        config = _config(tmp_path)
        _write_schools(config, [_school()])
        api = FakeApi(
            members={"Category:Acme College faculty": [
                "List of Acme College faculty", "Template:Acme", "Jane Doe"]},
            qids={"Jane Doe": "Q1"},
            ents={"Q1": _person("Q1", 3)},
        )

        _run(config, api)

        assert [p["name"] for p in _records(config)[0]["notable_faculty"]] == ["Jane Doe"]

    def test_a_school_with_nobody_gets_an_empty_list_not_a_padded_one(self, tmp_path: Path):
        config = _config(tmp_path)
        _write_schools(config, [_school()])

        summary = _run(config, FakeApi())

        assert _records(config)[0]["notable_faculty"] == []
        assert any("yielded nobody" in note for note in summary.notes)

    def test_a_thin_school_is_reported_rather_than_topped_up(self, tmp_path: Path):
        config = _config(tmp_path)
        _write_schools(config, [_school()])
        api = FakeApi(
            members={"Category:Acme College faculty": ["A", "B", "C"]},
            qids={"A": "Q1", "B": "Q2", "C": "Q3"},
            ents={q: _person(q, 5) for q in ("Q1", "Q2", "Q3")},
        )

        summary = _run(config, api)

        assert len(_records(config)[0]["notable_faculty"]) == 3
        assert any("fewer than 10" in note for note in summary.notes)


class TestWhatEachRecordSays:
    def _one(self, tmp_path: Path, entity: dict, **kwargs) -> dict:
        config = _config(tmp_path)
        _write_schools(config, [_school()])
        api = FakeApi(
            members={"Category:Acme College faculty": ["Jane Doe"]},
            qids={"Jane Doe": entity["id"]},
            ents={entity["id"]: entity},
            label_map={"Q169470": "physicist", "Q1622272": "university teacher"},
        )
        _run(config, api, **kwargs)
        return _records(config)[0]["notable_faculty"][0]

    def test_it_carries_what_they_are_known_for(self, tmp_path: Path):
        person = self._one(tmp_path, _person("Q1", 12, desc="American theoretical physicist"))

        assert person["known_for"] == "American theoretical physicist"

    def test_it_links_to_the_source_so_a_reader_can_check(self, tmp_path: Path):
        person = self._one(tmp_path, _person("Q1", 12))

        assert person["source_url"] == "https://en.wikipedia.org/wiki/Jane_Doe"
        assert person["source"] == "wikipedia"

    def test_a_living_professor_is_current(self, tmp_path: Path):
        assert self._one(tmp_path, _person("Q1", 12))["status"] == "current"

    def test_a_dead_professor_is_labelled_historical_not_dropped(self, tmp_path: Path):
        """Ansel Adams taught at ArtCenter and is much of why it is known. He
        belongs in the list — and must never read as someone teaching now."""
        person = self._one(tmp_path, _person("Q1", 40, dead=True))

        assert person["status"] == "historical"

    def test_fields_come_from_occupations(self, tmp_path: Path):
        person = self._one(
            tmp_path, _person("Q1", 12, occupations=["Q169470", "Q1622272"])
        )

        assert person["fields"] == ["physicist"], "'university teacher' says nothing useful"


class TestRanking:
    def test_the_widely_known_come_first(self, tmp_path: Path):
        config = _config(tmp_path)
        _write_schools(config, [_school()])
        api = FakeApi(
            members={"Category:Acme College faculty": ["Local Lecturer", "Famous Laureate"]},
            qids={"Local Lecturer": "Q1", "Famous Laureate": "Q2"},
            ents={"Q1": _person("Q1", 1), "Q2": _person("Q2", 120)},
        )

        _run(config, api)

        assert [p["name"] for p in _records(config)[0]["notable_faculty"]] == [
            "Famous Laureate", "Local Lecturer",
        ]

    def test_the_list_is_capped(self, tmp_path: Path):
        config = _config(tmp_path)
        _write_schools(config, [_school()])
        names = [f"Person {i:03}" for i in range(40)]
        api = FakeApi(
            members={"Category:Acme College faculty": names},
            qids={n: f"Q{i}" for i, n in enumerate(names)},
            ents={f"Q{i}": _person(f"Q{i}", 10) for i in range(40)},
        )

        _run(config, api, per_school=20)

        assert len(_records(config)[0]["notable_faculty"]) == 20

    def test_order_is_stable_when_prominence_ties(self, tmp_path: Path):
        config = _config(tmp_path)
        _write_schools(config, [_school()])
        api = FakeApi(
            members={"Category:Acme College faculty": ["Zoe Zhang", "Amy Adams"]},
            qids={"Zoe Zhang": "Q1", "Amy Adams": "Q2"},
            ents={"Q1": _person("Q1", 7), "Q2": _person("Q2", 7)},
        )

        _run(config, api)

        assert [p["name"] for p in _records(config)[0]["notable_faculty"]] == [
            "Amy Adams", "Zoe Zhang",
        ]


class TestResumability:
    def test_a_done_school_is_not_looked_up_again(self, tmp_path: Path):
        config = _config(tmp_path)
        _write_schools(config, [_school()])
        api = FakeApi(members={"Category:Acme College faculty": []})

        _run(config, api)
        _run(config, api)

        assert len(api.calls) == 1

    def test_a_failure_is_retried_next_run(self, tmp_path: Path):
        config = _config(tmp_path)
        _write_schools(config, [_school()])

        class Boom(FakeApi):
            def category_members(self, category, *, cap=1500):
                raise RuntimeError("network gone")

        summary = _run(config, Boom())

        assert summary.failed == 1
        assert not _checkpoint(config).is_done("acme-college")

    def test_dry_run_makes_no_requests(self, tmp_path: Path):
        config = _config(tmp_path)
        _write_schools(config, [_school()])
        api = FakeApi()

        summary = _run(config, api, dry_run=True)

        assert api.calls == []
        assert _records(config) == []
        assert any("dry-run" in note for note in summary.notes)

    def test_non_us_schools_are_not_looked_up(self, tmp_path: Path):
        config = _config(tmp_path)
        abroad = School(school_id="ox", name="Oxford", slug="ox", country="UK",
                        homepage="https://ox.ac.uk")
        _write_schools(config, [abroad])
        api = FakeApi()

        _run(config, api)

        assert api.calls == []


class TestTierFile:
    def test_it_folds_the_jsonl_into_one_committed_file(self, tmp_path: Path):
        config = _config(tmp_path)
        _write_schools(config, [_school(), _school("bard-college", "Bard College")])
        api = FakeApi(
            members={
                "Category:Acme College faculty": ["Jane Doe"],
                "Category:Bard College faculty": [],
            },
            qids={"Jane Doe": "Q1"},
            ents={"Q1": _person("Q1", 9)},
        )
        _run(config, api)

        tier = tmp_path / "sources" / "notable_faculty.json"
        written = notable.write_tier_file(config.data_dir, tier)

        payload = json.loads(tier.read_text())
        assert written == 2
        assert payload["acme-college"]["notable_faculty"][0]["name"] == "Jane Doe"
        # Measured and empty, which the catalog renders as [] rather than null:
        # "we looked and found nobody" is not "nobody has looked".
        assert payload["bard-college"]["notable_faculty"] == []

    def test_a_rerun_of_one_school_corrects_it(self, tmp_path: Path):
        config = _config(tmp_path)
        path = Path(config.data_dir) / "notable_faculty.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"school_id": "a", "school_name": "A",
                        "notable_faculty": [{"name": "Stale"}]}) + "\n"
            + json.dumps({"school_id": "a", "school_name": "A",
                          "notable_faculty": [{"name": "Fresh"}]}) + "\n",
            encoding="utf-8",
        )

        notable.write_tier_file(config.data_dir, tmp_path / "tier.json")

        payload = json.loads((tmp_path / "tier.json").read_text())
        assert [p["name"] for p in payload["a"]["notable_faculty"]] == ["Fresh"]

    def test_it_refuses_to_write_from_nothing(self, tmp_path: Path):
        config = _config(tmp_path)

        with pytest.raises(notable.NotableError, match="Run `notable` first"):
            notable.write_tier_file(config.data_dir, tmp_path / "tier.json")


class TestRobotsExemption:
    """The exemption has to be narrow enough that it cannot become a way to
    crawl anything else around a robots rule."""

    @dataclass
    class DenyAll:
        def is_allowed(self, url: str, user_agent: str) -> bool:
            return False

        def crawl_delay(self, url: str) -> float | None:
            return None

        def sitemaps(self, url: str) -> list[str]:
            return []

    def test_the_two_api_endpoints_are_allowed(self):
        robots = ApiRobots(self.DenyAll())

        assert robots.is_allowed("https://en.wikipedia.org/w/api.php?action=query", "ua")
        assert robots.is_allowed("https://www.wikidata.org/w/api.php?action=wbgetentities", "ua")

    def test_wikipedia_article_html_is_still_refused(self):
        robots = ApiRobots(self.DenyAll())

        assert not robots.is_allowed("https://en.wikipedia.org/wiki/Noam_Chomsky", "ua")

    def test_every_other_host_is_still_delegated(self):
        robots = ApiRobots(self.DenyAll())

        assert not robots.is_allowed("https://www.acme.edu/faculty", "ua")
        assert not robots.is_allowed("https://en.wikipedia.org.evil.test/w/api.php", "ua")


def test_the_category_follows_from_the_school_name():
    assert notable.category_for(_school(name="Bard College")) == "Category:Bard College faculty"


class TestApiWrapper:
    """`MediaWikiApi` over a fake fetcher — the paging and error paths."""

    @dataclass
    class FakeHttp:
        bodies: list[str]
        urls: list[str] = field(default_factory=list)

        def fetch(self, url: str, *, method: str = "GET"):
            self.urls.append(url)

            @dataclass
            class R:
                body: str

            return R(self.bodies[len(self.urls) - 1])

    def test_it_follows_continuations(self):
        http = self.FakeHttp(bodies=[
            json.dumps({"query": {"categorymembers": [{"title": "A"}]},
                        "continue": {"cmcontinue": "x", "continue": "-||"}}),
            json.dumps({"query": {"categorymembers": [{"title": "B"}]}}),
        ])

        titles = MediaWikiApi(http).category_members("Category:X faculty")

        assert titles == ["A", "B"]
        assert "cmcontinue=x" in http.urls[1]

    def test_an_api_error_is_raised_not_silently_empty(self):
        http = self.FakeHttp(bodies=[json.dumps({"error": {"info": "maxlag exceeded"}})])

        with pytest.raises(Exception, match="maxlag"):
            MediaWikiApi(http).category_members("Category:X faculty")


class TestCategoryResolution:
    """The catalog's name for a school is often not Wikipedia's. Measured on
    the 20 schools that first came back empty: "Georgia Institute of
    Technology" is filed under "Georgia Tech", "University of Maryland" under
    "University of Maryland, College Park", and Hamilton College's category is
    "Hamilton College (New York) faculty". Each is a real professor list that
    the plain name missed."""

    @dataclass
    class ResolvingApi(FakeApi):
        canonical: dict[str, str] = field(default_factory=dict)
        articles: dict[str, str] = field(default_factory=dict)
        searched: dict[str, str] = field(default_factory=dict)
        lookups: list[str] = field(default_factory=list)

        def canonical_title(self, name: str) -> str | None:
            self.lookups.append(f"canonical:{name}")
            return self.canonical.get(name)

        def search_article(self, name: str) -> str | None:
            self.lookups.append(f"article:{name}")
            return self.articles.get(name)

        def search_faculty_category(self, name: str) -> str | None:
            self.lookups.append(f"search:{name}")
            return self.searched.get(name)

    def _run_one(self, tmp_path: Path, api, name="Georgia Institute of Technology"):
        config = _config(tmp_path)
        _write_schools(config, [_school("gt", name)])
        _run(config, api)
        return _records(config)[0]

    def test_the_plain_name_is_tried_first_and_costs_no_extra_lookup(self, tmp_path: Path):
        api = self.ResolvingApi(
            members={"Category:Georgia Institute of Technology faculty": ["Jane Doe"]},
            qids={"Jane Doe": "Q1"}, ents={"Q1": _person("Q1", 5)},
        )

        record = self._run_one(tmp_path, api)

        assert [p["name"] for p in record["notable_faculty"]] == ["Jane Doe"]
        assert api.lookups == [], "a school that resolves directly needs no fallback"

    def test_a_redirect_finds_the_real_category(self, tmp_path: Path):
        api = self.ResolvingApi(
            members={"Category:Georgia Tech faculty": ["Jane Doe"]},
            qids={"Jane Doe": "Q1"}, ents={"Q1": _person("Q1", 5)},
            canonical={"Georgia Institute of Technology": "Georgia Tech"},
        )

        record = self._run_one(tmp_path, api)

        assert [p["name"] for p in record["notable_faculty"]] == ["Jane Doe"]

    def test_an_irregular_category_name_is_searched_for(self, tmp_path: Path):
        api = self.ResolvingApi(
            members={"Category:Hamilton College (New York) faculty": ["Jane Doe"]},
            qids={"Jane Doe": "Q1"}, ents={"Q1": _person("Q1", 5)},
            canonical={"Hamilton College": "Hamilton College"},
            searched={"Hamilton College": "Category:Hamilton College (New York) faculty"},
        )

        record = self._run_one(tmp_path, api, name="Hamilton College")

        assert [p["name"] for p in record["notable_faculty"]] == ["Jane Doe"]

    def test_a_parenthetical_the_catalog_added_is_searched_past(self, tmp_path: Path):
        """"Binghamton University (SUNY)" is neither a Wikipedia title nor a
        redirect — the parenthetical is this catalog's, not Wikipedia's."""
        api = self.ResolvingApi(
            members={"Category:Binghamton University faculty": ["Jane Doe"]},
            qids={"Jane Doe": "Q1"}, ents={"Q1": _person("Q1", 5)},
            articles={"Binghamton University (SUNY)": "Binghamton University"},
        )

        record = self._run_one(tmp_path, api, name="Binghamton University (SUNY)")

        assert [p["name"] for p in record["notable_faculty"]] == ["Jane Doe"]

    def test_a_school_with_no_category_anywhere_is_still_honestly_empty(self, tmp_path: Path):
        api = self.ResolvingApi(canonical={}, searched={})

        record = self._run_one(tmp_path, api, name="American Academy of Dramatic Arts")

        assert record["notable_faculty"] == []

    def test_the_category_actually_used_is_recorded(self, tmp_path: Path):
        """So a thin result can be checked against the right category rather
        than guessed at."""
        api = self.ResolvingApi(
            members={"Category:Georgia Tech faculty": ["Jane Doe"]},
            qids={"Jane Doe": "Q1"}, ents={"Q1": _person("Q1", 5)},
            canonical={"Georgia Institute of Technology": "Georgia Tech"},
        )

        record = self._run_one(tmp_path, api)

        assert record["category"] == "Category:Georgia Tech faculty"
