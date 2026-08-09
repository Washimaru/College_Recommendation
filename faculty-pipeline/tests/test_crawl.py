from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from faculty_pipeline.config import Config
from faculty_pipeline.models import Directory
from faculty_pipeline.services.checkpoint import CheckpointStore
from faculty_pipeline.services.http_client import FetchResult
from faculty_pipeline.services.robots import RobotsDisallowedError
from faculty_pipeline.stages import crawl
from faculty_pipeline.utils import normalize_url, registrable_domain

FIXTURES = Path(__file__).parent / "fixtures" / "crawl"
BASE = "https://www.acmecollege.edu"


def _html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _config(tmp_path: Path, **overrides: object) -> Config:
    return Config(
        input_path=tmp_path / "schools.json",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        checkpoint_dir=tmp_path / "checkpoints",
        log_dir=tmp_path / "logs",
        **overrides,
    )


def _directory(
    school_id: str = "acme-college",
    urls: list[str] | None = None,
    profile_urls: list[str] | None = None,
) -> Directory:
    return Directory(
        school_id=school_id,
        directory_urls=urls if urls is not None else [f"{BASE}/faculty"],
        profile_urls=profile_urls,
        discovery_method="sitemap" if profile_urls else "heuristic",
        robots_allowed=True,
        confidence=0.9,
    )


def _write_directories(config: Config, directories: list[Directory]) -> None:
    path = Path(config.data_dir) / "directories.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(d.model_dump_json() for d in directories) + "\n", encoding="utf-8"
    )


def _fetch_result(status: int, body: str, url: str) -> FetchResult:
    return FetchResult(
        status=status, final_url=url, body=body, from_cache=False, cache_path=Path("/dev/null")
    )


@dataclass
class FakeHttpClient:
    """Maps url -> FetchResult; unmapped URLs raise (a dead link / network
    failure, same posture as test_discover.py's fake). `loop_prefix`, when
    set, synthesizes an endless `?n=<k>` pagination chain for URLs under that
    prefix — used to prove `max_directory_pages` binds against genuinely
    unbounded pagination, not just a fixed fixture set."""

    pages: dict[str, FetchResult] = field(default_factory=dict)
    disallowed: set[str] = field(default_factory=set)
    calls: list[str] = field(default_factory=list)
    loop_prefix: str | None = None

    def fetch(self, url: str, *, method: str = "GET") -> FetchResult:
        self.calls.append(url)
        if url in self.disallowed:
            raise RobotsDisallowedError(url)
        if url in self.pages:
            return self.pages[url]
        if self.loop_prefix is not None and url.startswith(self.loop_prefix):
            n = int(parse_qs(urlsplit(url).query).get("n", ["0"])[0])
            body = (
                '<html><body><a href="/faculty/static-prof">Static Prof</a>'
                f'<a href="{self.loop_prefix}?n={n + 1}" rel="next">Next</a></body></html>'
            )
            return FetchResult(
                status=200, final_url=url, body=body, from_cache=False, cache_path=Path("/dev/null")
            )
        raise RuntimeError(f"no fixture for {url}")


def _checkpoint(config: Config) -> CheckpointStore:
    return CheckpointStore(Path(config.checkpoint_dir) / "crawl.json")


def _run(
    config: Config, checkpoint: CheckpointStore, http_client: FakeHttpClient, **kwargs: object
):
    logger = logging.getLogger("faculty_pipeline.test_crawl")
    return crawl.run(config, checkpoint, logger, http_client, **kwargs)


def _read_profiles(config: Config) -> list[dict]:
    path = Path(config.data_dir) / "profiles_raw.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _realistic_pages() -> dict[str, FetchResult]:
    """A six-page directory: entrypoint + three A-Z letter filters + a
    rel=next continuation + a numbered page-3, five distinct professors
    total, plus one off-domain aggregator link that must never be fetched."""
    letter_body = _html("directory_letter_page.html")
    return {
        f"{BASE}/faculty": _fetch_result(200, _html("directory_index.html"), f"{BASE}/faculty"),
        f"{BASE}/faculty?letter=A": _fetch_result(200, letter_body, f"{BASE}/faculty?letter=A"),
        f"{BASE}/faculty?letter=B": _fetch_result(200, letter_body, f"{BASE}/faculty?letter=B"),
        f"{BASE}/faculty?letter=C": _fetch_result(200, letter_body, f"{BASE}/faculty?letter=C"),
        f"{BASE}/faculty/more": _fetch_result(
            200, _html("directory_more.html"), f"{BASE}/faculty/more"
        ),
        f"{BASE}/faculty/more?page=3": _fetch_result(
            200, _html("directory_page3.html"), f"{BASE}/faculty/more?page=3"
        ),
        f"{BASE}/faculty/jane-doe": _fetch_result(
            200, _html("profile_jane_doe.html"), f"{BASE}/faculty/jane-doe"
        ),
        f"{BASE}/faculty/john-smith": _fetch_result(
            200, _html("profile_minimal.html"), f"{BASE}/faculty/john-smith"
        ),
        f"{BASE}/faculty/amy-chen": _fetch_result(
            200, _html("profile_minimal.html"), f"{BASE}/faculty/amy-chen"
        ),
        f"{BASE}/faculty/carlos-diaz": _fetch_result(
            200, _html("profile_minimal.html"), f"{BASE}/faculty/carlos-diaz"
        ),
        f"{BASE}/faculty/erin-atwell": _fetch_result(
            200, _html("profile_minimal.html"), f"{BASE}/faculty/erin-atwell"
        ),
    }


ALL_REALISTIC_PROFILE_URLS = {
    f"{BASE}/faculty/jane-doe",
    f"{BASE}/faculty/john-smith",
    f"{BASE}/faculty/amy-chen",
    f"{BASE}/faculty/carlos-diaz",
    f"{BASE}/faculty/erin-atwell",
}


# -- realistic enumeration + A-Z pagination vs. profile distinction --------


def test_realistic_directory_enumerates_profiles_and_follows_pagination(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    _write_directories(config, [_directory()])
    http_client = FakeHttpClient(pages=_realistic_pages())

    summary = _run(config, _checkpoint(config), http_client)

    rows = _read_profiles(config)
    urls = {r["profile_url"] for r in rows}
    assert urls == ALL_REALISTIC_PROFILE_URLS
    assert summary.processed == 5
    assert summary.failed == 0

    # A-Z letter links and the "more"/page=3 pagination were fetched as
    # directory pages (in search of more people) and never stored as
    # profiles themselves.
    assert f"{BASE}/faculty?letter=B" not in urls
    assert f"{BASE}/faculty/more" not in urls
    assert f"{BASE}/faculty?letter=B" in http_client.calls
    assert f"{BASE}/faculty/more?page=3" in http_client.calls

    # The off-domain aggregator link was never even fetched.
    assert not any("ratemyprofessors" in call for call in http_client.calls)


def test_off_domain_links_are_rejected_before_any_fetch(tmp_path: Path) -> None:
    config = _config(tmp_path)
    http_client = FakeHttpClient(pages=_realistic_pages())

    result = crawl._enumerate_directory(
        config, http_client, [f"{BASE}/faculty"], "acme-college", logging.getLogger("t")
    )

    profile_urls = {u for u, _ in result.profile_entries}
    assert not any("ratemyprofessors" in u for u in profile_urls)
    assert not any("ratemyprofessors" in c for c in http_client.calls)


# -- URL normalization / dedupe ---------------------------------------------


def test_trailing_slash_and_fragment_variants_dedupe_to_one_profile(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_directories(
        config, [_directory(urls=[f"{BASE}/dept-a", f"{BASE}/dept-b"])]
    )
    http_client = FakeHttpClient(
        pages={
            f"{BASE}/dept-a": _fetch_result(200, _html("directory_dup_a.html"), f"{BASE}/dept-a"),
            f"{BASE}/dept-b": _fetch_result(200, _html("directory_dup_b.html"), f"{BASE}/dept-b"),
            f"{BASE}/faculty/jane-doe": _fetch_result(
                200, _html("profile_jane_doe.html"), f"{BASE}/faculty/jane-doe"
            ),
        }
    )

    summary = _run(config, _checkpoint(config), http_client)

    rows = _read_profiles(config)
    assert len(rows) == 1
    assert rows[0]["profile_url"] == f"{BASE}/faculty/jane-doe"
    assert summary.processed == 1


def test_normalize_url_strips_fragment_and_trailing_slash() -> None:
    assert normalize_url("https://x.edu/faculty/jane-doe/#bio") == "https://x.edu/faculty/jane-doe"
    assert normalize_url("https://x.edu/faculty/jane-doe") == "https://x.edu/faculty/jane-doe"
    assert normalize_url("https://X.EDU/faculty") == "https://x.edu/faculty"


def test_normalize_url_preserves_query() -> None:
    assert normalize_url("https://x.edu/faculty?id=123") == "https://x.edu/faculty?id=123"


# -- max_profiles_per_school cap --------------------------------------------


def test_max_profiles_per_school_cap_binds(tmp_path: Path) -> None:
    config = _config(tmp_path, max_profiles_per_school=2)
    _write_directories(config, [_directory()])
    http_client = FakeHttpClient(
        pages={
            f"{BASE}/faculty": _fetch_result(200, _html("directory_many.html"), f"{BASE}/faculty"),
            f"{BASE}/faculty/prof-a": _fetch_result(
                200, _html("profile_minimal.html"), f"{BASE}/faculty/prof-a"
            ),
            f"{BASE}/faculty/prof-b": _fetch_result(
                200, _html("profile_minimal.html"), f"{BASE}/faculty/prof-b"
            ),
            f"{BASE}/faculty/prof-c": _fetch_result(
                200, _html("profile_minimal.html"), f"{BASE}/faculty/prof-c"
            ),
            f"{BASE}/faculty/prof-d": _fetch_result(
                200, _html("profile_minimal.html"), f"{BASE}/faculty/prof-d"
            ),
        }
    )

    summary = _run(config, _checkpoint(config), http_client)

    rows = _read_profiles(config)
    assert len(rows) == 2
    assert summary.processed == 2
    assert any("truncated at max_profiles_per_school=2" in note for note in summary.notes)
    # The truncated urls were never fetched at all (still on the server's
    # side of politeness), not fetched-then-discarded.
    assert f"{BASE}/faculty/prof-c" not in http_client.calls
    assert f"{BASE}/faculty/prof-d" not in http_client.calls


# -- max_directory_pages cap -------------------------------------------------


def test_max_directory_pages_caps_unbounded_pagination(tmp_path: Path) -> None:
    config = _config(tmp_path, max_directory_pages=3)
    _write_directories(config, [_directory(urls=[f"{BASE}/loop?n=0"])])
    http_client = FakeHttpClient(
        pages={
            f"{BASE}/faculty/static-prof": _fetch_result(
                200, _html("profile_minimal.html"), f"{BASE}/faculty/static-prof"
            ),
        },
        loop_prefix=f"{BASE}/loop",
    )

    summary = _run(config, _checkpoint(config), http_client)

    loop_calls = [c for c in http_client.calls if c.startswith(f"{BASE}/loop")]
    assert len(loop_calls) == 3  # capped, not infinite
    assert any("hit max_directory_pages=3" in note for note in summary.notes)
    # The one profile link that does exist was still found and fetched.
    assert summary.processed == 1


def test_cyclical_next_links_terminate_via_visited_dedupe(tmp_path: Path) -> None:
    config = _config(tmp_path)  # default max_directory_pages=20
    _write_directories(config, [_directory(urls=[f"{BASE}/cycle/a"])])
    http_client = FakeHttpClient(
        pages={
            f"{BASE}/cycle/a": _fetch_result(
                200, _html("directory_cycle_a.html"), f"{BASE}/cycle/a"
            ),
            f"{BASE}/cycle/b": _fetch_result(
                200, _html("directory_cycle_b.html"), f"{BASE}/cycle/b"
            ),
        }
    )

    # Must return promptly, not hang: a<->b keeps re-appearing but the
    # visited-set means each is only ever fetched once.
    _run(config, _checkpoint(config), http_client)

    assert http_client.calls.count(f"{BASE}/cycle/a") == 1
    assert http_client.calls.count(f"{BASE}/cycle/b") == 1


# -- robots-disallowed skip --------------------------------------------------


def test_robots_disallowed_profile_is_skipped_not_fetched(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_directories(config, [_directory()])
    disallowed_url = f"{BASE}/faculty/john-smith"
    http_client = FakeHttpClient(pages=_realistic_pages(), disallowed={disallowed_url})

    summary = _run(config, _checkpoint(config), http_client)

    rows = _read_profiles(config)
    urls = {r["profile_url"] for r in rows}
    assert disallowed_url not in urls
    assert urls == ALL_REALISTIC_PROFILE_URLS - {disallowed_url}
    assert summary.failed == 0  # a robots skip is not a failure
    assert _checkpoint(config).entry(disallowed_url) is None


# -- 404 / dead link handling -------------------------------------------------


def test_404_profile_is_recorded_and_checkpointed_done_not_retried(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_directories(config, [_directory(urls=[f"{BASE}/dept-a"])])
    dead_url = f"{BASE}/faculty/jane-doe"
    http_client = FakeHttpClient(
        pages={
            f"{BASE}/dept-a": _fetch_result(200, _html("directory_dup_a.html"), f"{BASE}/dept-a"),
            dead_url: _fetch_result(404, "<html><body>Not Found</body></html>", dead_url),
        }
    )

    summary = _run(config, _checkpoint(config), http_client)

    rows = _read_profiles(config)
    assert len(rows) == 1
    assert rows[0]["http_status"] == 404
    assert summary.processed == 1
    assert summary.failed == 0
    assert _checkpoint(config).is_done(dead_url) is True


def test_transport_failure_is_logged_and_marked_failed_not_fatal(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_directories(config, [_directory(urls=[f"{BASE}/dept-a"])])
    # jane-doe is linked from dept-a but has no fixture -> FakeHttpClient
    # raises, simulating a connection error surviving http_client's retries.
    http_client = FakeHttpClient(
        pages={
            f"{BASE}/dept-a": _fetch_result(200, _html("directory_dup_a.html"), f"{BASE}/dept-a"),
        }
    )

    summary = _run(config, _checkpoint(config), http_client)  # must not raise

    assert _read_profiles(config) == []
    assert summary.failed == 1
    entry = _checkpoint(config).entry(f"{BASE}/faculty/jane-doe")
    assert entry is not None
    assert entry.status == "failed"


# -- checkpoint resume --------------------------------------------------------


def test_checkpoint_resume_skips_already_done_profile(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_directories(config, [_directory()])
    http_client = FakeHttpClient(pages=_realistic_pages())
    checkpoint = _checkpoint(config)
    checkpoint.mark_done(f"{BASE}/faculty/jane-doe")

    summary = _run(config, checkpoint, http_client)

    assert f"{BASE}/faculty/jane-doe" not in http_client.calls
    rows = _read_profiles(config)
    urls = {r["profile_url"] for r in rows}
    assert f"{BASE}/faculty/jane-doe" not in urls
    assert urls == ALL_REALISTIC_PROFILE_URLS - {f"{BASE}/faculty/jane-doe"}
    assert summary.processed == 4
    assert summary.skipped >= 1


# -- needs_dynamic_render -----------------------------------------------------


def test_no_profile_links_flags_needs_dynamic_render(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_directories(config, [_directory()])
    http_client = FakeHttpClient(
        pages={
            f"{BASE}/faculty": _fetch_result(
                200, _html("directory_empty.html"), f"{BASE}/faculty"
            )
        }
    )

    summary = _run(config, _checkpoint(config), http_client)

    assert _read_profiles(config) == []
    assert summary.processed == 0
    assert summary.failed == 0
    assert any("needs_dynamic_render" in note for note in summary.notes)
    assert any("acme-college" in note for note in summary.notes)


# -- schools with no discovered directory are not crawl targets -------------


def test_school_with_no_directory_urls_is_skipped_entirely(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_directories(
        config,
        [
            Directory(
                school_id="nowhere-u",
                directory_urls=[],
                discovery_method="none",
                robots_allowed=True,
                confidence=0.0,
            )
        ],
    )
    http_client = FakeHttpClient()

    summary = _run(config, _checkpoint(config), http_client)

    assert http_client.calls == []
    assert _read_profiles(config) == []
    assert summary.processed == 0
    assert summary.failed == 0


# -- --limit / --school ------------------------------------------------------


def test_school_filter_processes_only_that_school(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_directories(
        config,
        [
            _directory(school_id="acme-college"),
            _directory(school_id="other-college", urls=[f"{BASE}/dept-a"]),
        ],
    )
    pages = dict(_realistic_pages())
    pages[f"{BASE}/dept-a"] = _fetch_result(
        200, _html("directory_dup_a.html"), f"{BASE}/dept-a"
    )
    http_client = FakeHttpClient(pages=pages)

    _run(config, _checkpoint(config), http_client, school_id="other-college")

    rows = _read_profiles(config)
    assert {r["school_id"] for r in rows} == {"other-college"}


def test_limit_caps_number_of_schools_processed(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_directories(
        config,
        [
            _directory(school_id="school-a", urls=[f"{BASE}/dept-a"]),
            _directory(school_id="school-b", urls=[f"{BASE}/dept-b"]),
        ],
    )
    http_client = FakeHttpClient(
        pages={
            f"{BASE}/dept-a": _fetch_result(200, _html("directory_dup_a.html"), f"{BASE}/dept-a"),
            f"{BASE}/dept-b": _fetch_result(200, _html("directory_dup_b.html"), f"{BASE}/dept-b"),
            f"{BASE}/faculty/jane-doe": _fetch_result(
                200, _html("profile_jane_doe.html"), f"{BASE}/faculty/jane-doe"
            ),
        }
    )

    summary = _run(config, _checkpoint(config), http_client, limit=1)

    rows = _read_profiles(config)
    assert {r["school_id"] for r in rows} == {"school-a"}
    assert summary.skipped >= 1


# -- dry-run / --dynamic / missing input -------------------------------------


def test_dry_run_makes_no_network_calls_and_writes_nothing(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_directories(config, [_directory()])
    http_client = FakeHttpClient(pages=_realistic_pages())

    summary = _run(config, _checkpoint(config), http_client, dry_run=True)

    assert http_client.calls == []
    assert not (Path(config.data_dir) / "profiles_raw.jsonl").exists()
    assert any("dry-run" in note for note in summary.notes)


def test_dynamic_flag_raises_not_implemented(tmp_path: Path) -> None:
    config = _config(tmp_path)
    _write_directories(config, [_directory()])
    http_client = FakeHttpClient(pages=_realistic_pages())

    with pytest.raises(crawl.CrawlError, match="dynamic"):
        _run(config, _checkpoint(config), http_client, dynamic=True)


def test_missing_directories_file_raises_crawl_error(tmp_path: Path) -> None:
    config = _config(tmp_path)
    http_client = FakeHttpClient()

    with pytest.raises(crawl.CrawlError, match="discover"):
        _run(config, _checkpoint(config), http_client)


# -- parse_hint ---------------------------------------------------------------


def test_parse_hint_splits_name_and_title_on_comma() -> None:
    hint = crawl._parse_hint(_html("profile_jane_doe.html"))
    assert hint == {"name": "Jane Doe", "title": "Professor of Biology"}


def test_parse_hint_falls_back_to_title_tag_without_comma() -> None:
    hint = crawl._parse_hint(_html("profile_minimal.html"))
    assert hint == {"name": "Carlos Diaz", "title": None}


def test_parse_hint_returns_none_for_page_with_no_heading_or_title() -> None:
    assert crawl._parse_hint("<html><body><p>nothing here</p></body></html>") == {
        "name": None,
        "title": None,
    }


# -- _classify_link -----------------------------------------------------------


def test_classify_link_az_letter_query_is_pagination_not_profile() -> None:
    kind = crawl._classify_link(
        f"{BASE}/faculty?letter=B", f"{BASE}/faculty", "B", rel=None
    )
    assert kind == "pagination"


def test_classify_link_rel_next_is_pagination() -> None:
    kind = crawl._classify_link(
        f"{BASE}/faculty/more", f"{BASE}/faculty", "Continue", rel="next"
    )
    assert kind == "pagination"


def test_classify_link_faculty_path_is_profile() -> None:
    kind = crawl._classify_link(
        f"{BASE}/faculty/jane-doe", f"{BASE}/faculty", "Jane Doe", rel=None
    )
    assert kind == "profile"


def test_classify_link_id_query_is_profile() -> None:
    kind = crawl._classify_link(
        f"{BASE}/directory/profile?id=123", f"{BASE}/directory", "Jane Doe", rel=None
    )
    assert kind == "profile"


def test_classify_link_unrelated_link_is_ignored() -> None:
    kind = crawl._classify_link(f"{BASE}/about", f"{BASE}/faculty", "About us", rel=None)
    assert kind == "ignore"


# -- registrable_domain --------------------------------------------------------


def test_registrable_domain_ignores_subdomain() -> None:
    assert registrable_domain("https://www.bard.edu/faculty") == "bard.edu"
    assert registrable_domain("https://math.bard.edu/people") == "bard.edu"


def test_registrable_domain_distinguishes_different_sites() -> None:
    assert registrable_domain("https://www.ratemyprofessors.com/x") != registrable_domain(
        "https://www.bard.edu/faculty"
    )


# ---------------------------------------------------------------------------
# Defects found on the first live run (Bard College)
# ---------------------------------------------------------------------------


class TestAssetLinksAreNotProfiles:
    """`?id=` is a real profile pattern, and also matches asset handlers.

    The live run fetched `tools.bard.edu/files/pr/main_news_image.php?id=21490`
    — a news JPEG — and stored it as a profile.
    """

    def test_the_real_jpeg_that_slipped_through(self):
        href = "https://tools.bard.edu/files/pr/main_news_image.php?id=21490"

        assert crawl._classify_link(href, "https://www.bard.edu/faculty/", "", None) == "ignore"

    def test_image_extensions_are_ignored(self):
        for href in (
            "https://x.edu/people/photo.jpg",
            "https://x.edu/profile/headshot.PNG",
            "https://x.edu/faculty/cv.pdf",
        ):
            assert crawl._classify_link(href, "https://x.edu/faculty/", "", None) == "ignore", href

    def test_a_genuine_profile_still_classifies(self):
        href = "https://www.bard.edu/faculty/details/?id=2891"

        assert crawl._classify_link(href, "https://www.bard.edu/faculty/", "", None) == "profile"


class TestAlphabeticallyPartialCapture:
    """A directory that server-renders only its 'A' section and loads B-Z by
    script hands back real, valid links — nothing errors, nothing 404s, and the
    run reports success having captured a fraction of the faculty."""

    def test_the_real_bard_capture_is_flagged(self):
        # Verbatim from the first live run: 17 profiles, every surname under A.
        urls = [
            f"https://www.bard.edu/faculty/{slug}"
            for slug in (
                "susan-aberth", "ziad-abu-rish", "kenyon-adams", "ross-exo-adams",
                "folarin-ajibade", "jasmine-akiyama-kim", "kathryn-aldous",
                "richard-aldous", "jaime-osterman-alves", "craig-anderson",
                "sven-anderson", "victor-apryshchenko", "nathanael-aschenbrenner",
                "ephraim-asili", "andrew-atwell", "erin-atwell", "jordan-ayala",
            )
        ]

        assert crawl._looks_alphabetically_partial(urls) is True

    def test_a_spread_of_surnames_is_not_flagged(self):
        urls = [
            f"https://x.edu/faculty/{slug}"
            for slug in (
                "susan-aberth", "john-brown", "amy-chen", "raj-desai", "li-evans",
                "omar-farouk", "gita-ghosh", "hans-iqbal", "ines-jansen",
            )
        ]

        assert crawl._looks_alphabetically_partial(urls) is False

    def test_surname_first_slugs_are_caught_too(self):
        # Some sites use `aberth-susan`; the concentration is on the other token.
        urls = [
            f"https://x.edu/people/{slug}"
            for slug in (
                "aberth-susan", "adams-kenyon", "ajibade-folarin", "aldous-kathryn",
                "anderson-craig", "asili-ephraim", "atwell-andrew", "ayala-jordan",
            )
        ]

        assert crawl._looks_alphabetically_partial(urls) is True

    def test_a_genuinely_small_department_is_not_flagged(self):
        """Four people sharing an initial is coincidence, not truncation."""
        urls = [
            f"https://x.edu/faculty/{slug}"
            for slug in ("amy-adams", "alan-archer", "ada-avery", "ann-ash")
        ]

        assert crawl._looks_alphabetically_partial(urls) is False


# ---------------------------------------------------------------------------
# Sitemap profiles (the discovery-recall fix): crawl what discover.py already
# found in the sitemap instead of enumerating the directory page's links.
# ---------------------------------------------------------------------------


def test_school_with_only_profile_urls_and_no_directory_urls_is_still_a_target(
    tmp_path: Path,
) -> None:
    """discover.py can produce a Directory with directory_urls: [] and a
    populated profile_urls (no directory-index candidate resolved, but the
    sitemap profile cluster is self-evident on its own — e.g. the live
    Auburn/ASU runs). Such a school must still be crawled, not silently
    dropped by the directory_urls-only "has anything to crawl" filter."""
    config = _config(tmp_path)
    profile_urls = [f"{BASE}/directory/faculty/prof-{i}.html" for i in range(5)]
    _write_directories(config, [_directory(urls=[], profile_urls=profile_urls)])
    http_client = FakeHttpClient(
        pages={url: _fetch_result(200, _html("profile_minimal.html"), url) for url in profile_urls}
    )

    summary = _run(config, _checkpoint(config), http_client)

    rows = _read_profiles(config)
    assert {r["profile_url"] for r in rows} == set(profile_urls)
    assert summary.processed == 5
    assert summary.skipped == 0


def test_crawl_uses_sitemap_profiles_instead_of_enumerating(tmp_path: Path) -> None:
    """Agnes Scott-style: discover.py found 124 (here, 6) profile urls
    directly in the sitemap. Crawl must fetch exactly those, and must never
    fetch/enumerate the directory page at all — enumeration is what produced
    the 17-of-several-hundred partial capture this feature replaces."""
    config = _config(tmp_path)
    profile_urls = [f"{BASE}/directory/faculty/prof-{i}.html" for i in range(6)]
    _write_directories(
        config,
        [_directory(urls=[f"{BASE}/directory/faculty/index.html"], profile_urls=profile_urls)],
    )
    http_client = FakeHttpClient(
        pages={url: _fetch_result(200, _html("profile_minimal.html"), url) for url in profile_urls}
    )

    summary = _run(config, _checkpoint(config), http_client)

    rows = _read_profiles(config)
    assert {r["profile_url"] for r in rows} == set(profile_urls)
    assert summary.processed == 6
    assert summary.failed == 0
    # The directory index page itself was never fetched: no enumeration.
    assert f"{BASE}/directory/faculty/index.html" not in http_client.calls
    assert set(http_client.calls) == set(profile_urls)


def test_sitemap_profiles_use_the_directory_index_as_directory_url(tmp_path: Path) -> None:
    config = _config(tmp_path)
    profile_urls = [f"{BASE}/directory/faculty/prof-{i}.html" for i in range(5)]
    index_url = f"{BASE}/directory/faculty/index.html"
    _write_directories(config, [_directory(urls=[index_url], profile_urls=profile_urls)])
    http_client = FakeHttpClient(
        pages={url: _fetch_result(200, _html("profile_minimal.html"), url) for url in profile_urls}
    )

    _run(config, _checkpoint(config), http_client)

    rows = _read_profiles(config)
    assert all(r["directory_url"] == index_url for r in rows)


def test_sitemap_profiles_with_no_directory_url_use_sentinel(tmp_path: Path) -> None:
    """A cluster found with no directory-index candidate at all
    (discover.py's "no candidates but has profile_urls" case) still needs
    some non-empty directory_url for the RawProfile schema."""
    config = _config(tmp_path)
    profile_urls = [f"{BASE}/directory/faculty/prof-{i}.html" for i in range(5)]
    _write_directories(config, [_directory(urls=[], profile_urls=profile_urls)])
    http_client = FakeHttpClient(
        pages={url: _fetch_result(200, _html("profile_minimal.html"), url) for url in profile_urls}
    )

    _run(config, _checkpoint(config), http_client)

    rows = _read_profiles(config)
    assert all(r["directory_url"] == "sitemap" for r in rows)


def test_sitemap_profiles_respect_max_profiles_per_school_cap(tmp_path: Path) -> None:
    config = _config(tmp_path, max_profiles_per_school=2)
    profile_urls = [f"{BASE}/directory/faculty/prof-{i}.html" for i in range(5)]
    _write_directories(config, [_directory(profile_urls=profile_urls)])
    http_client = FakeHttpClient(
        pages={url: _fetch_result(200, _html("profile_minimal.html"), url) for url in profile_urls}
    )

    summary = _run(config, _checkpoint(config), http_client)

    rows = _read_profiles(config)
    assert len(rows) == 2
    assert summary.processed == 2
    assert any("truncated at max_profiles_per_school=2" in note for note in summary.notes)


def test_sitemap_profiles_respect_robots_gate(tmp_path: Path) -> None:
    config = _config(tmp_path)
    profile_urls = [f"{BASE}/directory/faculty/prof-{i}.html" for i in range(5)]
    disallowed = profile_urls[0]
    _write_directories(config, [_directory(profile_urls=profile_urls)])
    http_client = FakeHttpClient(
        pages={url: _fetch_result(200, _html("profile_minimal.html"), url) for url in profile_urls},
        disallowed={disallowed},
    )

    summary = _run(config, _checkpoint(config), http_client)

    rows = _read_profiles(config)
    assert disallowed not in {r["profile_url"] for r in rows}
    assert summary.failed == 0


def test_sitemap_profiles_checkpoint_per_url_same_as_enumeration(tmp_path: Path) -> None:
    config = _config(tmp_path)
    profile_urls = [f"{BASE}/directory/faculty/prof-{i}.html" for i in range(5)]
    _write_directories(config, [_directory(profile_urls=profile_urls)])
    checkpoint = _checkpoint(config)
    checkpoint.mark_done(profile_urls[0])
    http_client = FakeHttpClient(
        pages={url: _fetch_result(200, _html("profile_minimal.html"), url) for url in profile_urls}
    )

    summary = _run(config, checkpoint, http_client)

    assert profile_urls[0] not in http_client.calls
    assert summary.processed == 4
    assert summary.skipped >= 1


def test_sitemap_profiles_alphabetic_partial_is_still_a_safety_net(tmp_path: Path) -> None:
    """Should now rarely fire, per the plan — but stays wired: if a
    sitemap-derived cluster is somehow all one letter, it is still flagged
    PARTIAL, not silently treated as complete."""
    config = _config(tmp_path)
    profile_urls = [
        f"{BASE}/directory/faculty/{slug}"
        for slug in (
            "susan-aberth", "ziad-abu-rish", "kenyon-adams", "ross-exo-adams",
            "folarin-ajibade", "jasmine-akiyama-kim", "kathryn-aldous",
            "richard-aldous", "jaime-osterman-alves", "craig-anderson",
        )
    ]
    _write_directories(config, [_directory(profile_urls=profile_urls)])
    http_client = FakeHttpClient(
        pages={url: _fetch_result(200, _html("profile_minimal.html"), url) for url in profile_urls}
    )

    summary = _run(config, _checkpoint(config), http_client)

    assert summary.processed == len(profile_urls)  # still crawled, not discarded
    assert any("PARTIAL" in note for note in summary.notes)


def test_sitemap_profiles_skip_needs_dynamic_render_path(tmp_path: Path) -> None:
    """Sitemap profiles never go through _enumerate_directory, so the
    JS-rendering-detection note must not appear for this path."""
    config = _config(tmp_path)
    profile_urls = [f"{BASE}/directory/faculty/prof-{i}.html" for i in range(5)]
    _write_directories(config, [_directory(profile_urls=profile_urls)])
    http_client = FakeHttpClient(
        pages={url: _fetch_result(200, _html("profile_minimal.html"), url) for url in profile_urls}
    )

    summary = _run(config, _checkpoint(config), http_client)

    assert not any("needs_dynamic_render" in note for note in summary.notes)
    assert any("taken directly from the sitemap" in note for note in summary.notes)
