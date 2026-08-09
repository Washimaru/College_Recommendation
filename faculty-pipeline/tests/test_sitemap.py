from __future__ import annotations

import gzip
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from faculty_pipeline.config import Config
from faculty_pipeline.services.http_client import FetchResult
from faculty_pipeline.services.robots import RobotsDisallowedError
from faculty_pipeline.services.sitemap import (
    discover_sitemap_urls,
    find_directory_pages,
    find_profile_clusters,
    largest_profile_cluster,
)

FIXTURES = Path(__file__).parent / "fixtures" / "sitemap"


def _xml(name: str) -> str:
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


def _fetch_result(status: int, body: str, url: str) -> FetchResult:
    return FetchResult(
        status=status, final_url=url, body=body, from_cache=False, cache_path=Path("/dev/null")
    )


@dataclass
class FakeHttpClient:
    pages: dict[str, FetchResult] = field(default_factory=dict)
    disallowed: set[str] = field(default_factory=set)
    calls: list[str] = field(default_factory=list)

    def fetch(self, url: str, *, method: str = "GET") -> FetchResult:
        self.calls.append(url)
        if url in self.disallowed:
            raise RobotsDisallowedError(url)
        if url in self.pages:
            return self.pages[url]
        raise RuntimeError(f"no fixture for {url}")


@dataclass
class FakeRobots:
    """Maps homepage -> advertised sitemap URLs. Empty/missing => none
    advertised, so discover_sitemap_urls falls back to `/sitemap.xml`."""

    advertised: dict[str, list[str]] = field(default_factory=dict)

    def sitemaps(self, url: str) -> list[str]:
        return list(self.advertised.get(url, []))


def _logger() -> logging.Logger:
    return logging.getLogger("faculty_pipeline.test_sitemap")


# -- robots-advertised sitemap -----------------------------------------------


def test_robots_advertised_sitemap_is_used(tmp_path: Path) -> None:
    config = _config(tmp_path)
    sitemap_url = "https://www.agnesscott.edu/sitemap.xml"
    http_client = FakeHttpClient(
        pages={sitemap_url: _fetch_result(200, _xml("agnes_scott_urlset.xml"), sitemap_url)}
    )
    robots = FakeRobots(advertised={"https://www.agnesscott.edu": [sitemap_url]})

    result = discover_sitemap_urls(
        config, http_client, robots, "https://www.agnesscott.edu", _logger()
    )

    assert len(result.urls) == 32
    assert "https://www.agnesscott.edu/directory/faculty/index.html" in result.urls
    assert result.documents_fetched == 1
    assert result.truncated is False
    # No second fetch path: the fallback /sitemap.xml URL is never tried
    # once robots already advertised the real one.
    assert http_client.calls == [sitemap_url]


# -- /sitemap.xml fallback ----------------------------------------------------


def test_falls_back_to_sitemap_xml_when_robots_advertises_none(tmp_path: Path) -> None:
    config = _config(tmp_path)
    homepage = "https://www.agnesscott.edu"
    fallback_url = "https://www.agnesscott.edu/sitemap.xml"
    http_client = FakeHttpClient(
        pages={fallback_url: _fetch_result(200, _xml("agnes_scott_urlset.xml"), fallback_url)}
    )
    robots = FakeRobots()  # advertises nothing

    result = discover_sitemap_urls(config, http_client, robots, homepage, _logger())

    assert http_client.calls == [fallback_url]
    assert len(result.urls) == 32


def test_no_sitemap_at_all_returns_empty_not_raises(tmp_path: Path) -> None:
    config = _config(tmp_path)
    homepage = "https://www.noreach.edu"
    http_client = FakeHttpClient(pages={})  # the fallback fetch 404s / has no fixture
    robots = FakeRobots()

    result = discover_sitemap_urls(config, http_client, robots, homepage, _logger())

    assert result.urls == []
    assert result.truncated is False


def test_404_sitemap_returns_empty(tmp_path: Path) -> None:
    config = _config(tmp_path)
    homepage = "https://www.noreach.edu"
    url = "https://www.noreach.edu/sitemap.xml"
    http_client = FakeHttpClient(pages={url: _fetch_result(404, "not found", url)})
    robots = FakeRobots()

    result = discover_sitemap_urls(config, http_client, robots, homepage, _logger())

    assert result.urls == []


def test_robots_disallowed_sitemap_returns_empty_not_raises(tmp_path: Path) -> None:
    config = _config(tmp_path)
    homepage = "https://www.noreach.edu"
    url = "https://www.noreach.edu/sitemap.xml"
    http_client = FakeHttpClient(disallowed={url})
    robots = FakeRobots()

    result = discover_sitemap_urls(config, http_client, robots, homepage, _logger())

    assert result.urls == []


# -- sitemap-index recursion (Auburn) -----------------------------------------


def test_sitemap_index_recurses_into_leaf_sitemap(tmp_path: Path) -> None:
    config = _config(tmp_path)
    homepage = "https://www.auburn.edu"
    index_url = "https://www.auburn.edu/sitemap.xml"
    leaf_url = "https://www.auburn.edu/sitemap-main.xml"
    http_client = FakeHttpClient(
        pages={
            index_url: _fetch_result(200, _xml("sitemap_index.xml"), index_url),
            leaf_url: _fetch_result(200, _xml("sitemap_main.xml"), leaf_url),
        }
    )
    robots = FakeRobots(advertised={homepage: [index_url]})

    result = discover_sitemap_urls(config, http_client, robots, homepage, _logger())

    assert result.documents_fetched == 2  # the index itself + the one leaf sitemap
    assert len(result.urls) == 6
    assert "https://www.auburn.edu/directory/faculty/adams-tom.html" in result.urls
    # The index document's own URL never leaks into the candidate url list.
    assert index_url not in result.urls
    assert leaf_url not in result.urls


# -- caps ----------------------------------------------------------------------


def test_max_sitemap_documents_caps_recursion(tmp_path: Path) -> None:
    """A pathological sitemap index with many leaf sitemaps stops recursing
    once max_sitemap_documents fetch attempts have been made."""
    config = _config(tmp_path, max_sitemap_documents=2)
    homepage = "https://www.manyleaves.edu"
    index_url = "https://www.manyleaves.edu/sitemap.xml"
    leaves = [f"https://www.manyleaves.edu/sitemap-{i}.xml" for i in range(5)]
    index_open = "<?xml version='1.0'?><sitemapindex xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
    index_xml = (
        index_open
        + "".join(f"<sitemap><loc>{leaf}</loc></sitemap>" for leaf in leaves)
        + "</sitemapindex>"
    )
    pages = {index_url: _fetch_result(200, index_xml, index_url)}
    for leaf in leaves:
        pages[leaf] = _fetch_result(
            200,
            "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
            f"<url><loc>{leaf}/faculty/person.html</loc></url></urlset>",
            leaf,
        )
    http_client = FakeHttpClient(pages=pages)
    robots = FakeRobots(advertised={homepage: [index_url]})

    result = discover_sitemap_urls(config, http_client, robots, homepage, _logger())

    assert result.documents_fetched == 2  # index + exactly one leaf, then the cap bites
    assert result.truncated is True
    assert len(result.urls) == 1


def test_max_sitemap_urls_caps_collected_urls(tmp_path: Path) -> None:
    config = _config(tmp_path, max_sitemap_urls=5)
    homepage = "https://www.agnesscott.edu"
    url = "https://www.agnesscott.edu/sitemap.xml"
    http_client = FakeHttpClient(
        pages={url: _fetch_result(200, _xml("agnes_scott_urlset.xml"), url)}
    )
    robots = FakeRobots(advertised={homepage: [url]})

    result = discover_sitemap_urls(config, http_client, robots, homepage, _logger())

    assert len(result.urls) == 5
    assert result.truncated is True


# -- gzip ------------------------------------------------------------------


def test_gzip_sitemap_is_decompressed(tmp_path: Path) -> None:
    config = _config(tmp_path)
    homepage = "https://www.agnesscott.edu"
    url = "https://www.agnesscott.edu/sitemap.xml.gz"
    xml_bytes = _xml("agnes_scott_urlset.xml").encode("utf-8")
    gzipped_as_text = gzip.compress(xml_bytes).decode("latin-1")
    http_client = FakeHttpClient(pages={url: _fetch_result(200, gzipped_as_text, url)})
    robots = FakeRobots(advertised={homepage: [url]})

    result = discover_sitemap_urls(config, http_client, robots, homepage, _logger())

    assert len(result.urls) == 32
    assert "https://www.agnesscott.edu/directory/faculty/index.html" in result.urls


def test_malformed_gzip_returns_empty_not_raises(tmp_path: Path) -> None:
    config = _config(tmp_path)
    homepage = "https://www.agnesscott.edu"
    url = "https://www.agnesscott.edu/sitemap.xml.gz"
    http_client = FakeHttpClient(pages={url: _fetch_result(200, "not actually gzip", url)})
    robots = FakeRobots(advertised={homepage: [url]})

    result = discover_sitemap_urls(config, http_client, robots, homepage, _logger())

    assert result.urls == []


# -- malformed XML -------------------------------------------------------------


def test_malformed_xml_returns_empty_not_raises(tmp_path: Path) -> None:
    config = _config(tmp_path)
    homepage = "https://www.brokensite.edu"
    url = "https://www.brokensite.edu/sitemap.xml"
    http_client = FakeHttpClient(pages={url: _fetch_result(200, _xml("malformed.xml"), url)})
    robots = FakeRobots(advertised={homepage: [url]})

    result = discover_sitemap_urls(config, http_client, robots, homepage, _logger())

    assert result.urls == []
    assert result.documents_fetched == 1


def test_transport_failure_on_one_document_does_not_abort_others(tmp_path: Path) -> None:
    config = _config(tmp_path)
    homepage = "https://www.auburn.edu"
    index_url = "https://www.auburn.edu/sitemap.xml"
    dead_leaf = "https://www.auburn.edu/sitemap-dead.xml"
    good_leaf = "https://www.auburn.edu/sitemap-main.xml"
    index_xml = (
        "<?xml version='1.0'?><sitemapindex xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
        f"<sitemap><loc>{dead_leaf}</loc></sitemap>"
        f"<sitemap><loc>{good_leaf}</loc></sitemap>"
        "</sitemapindex>"
    )
    http_client = FakeHttpClient(
        pages={
            index_url: _fetch_result(200, index_xml, index_url),
            good_leaf: _fetch_result(200, _xml("sitemap_main.xml"), good_leaf),
            # dead_leaf has no fixture -> FakeHttpClient raises RuntimeError
        }
    )
    robots = FakeRobots(advertised={homepage: [index_url]})

    result = discover_sitemap_urls(config, http_client, robots, homepage, _logger())

    assert len(result.urls) == 6  # sitemap_main.xml's urls still collected


# -- classification: directory pages vs. profile clusters --------------------


def test_find_directory_pages_identifies_the_index() -> None:
    urls = [
        "https://www.agnesscott.edu/",
        "https://www.agnesscott.edu/directory/faculty/index.html",
        "https://www.agnesscott.edu/directory/faculty/abrahao-thalita.html",
        "https://www.agnesscott.edu/about/history.html",
    ]

    pages = find_directory_pages(urls)

    assert pages == ["https://www.agnesscott.edu/directory/faculty/index.html"]


def test_find_directory_pages_matches_a_bare_trailing_path() -> None:
    urls = ["https://x.edu/faculty", "https://x.edu/people/", "https://x.edu/about"]

    pages = find_directory_pages(urls)

    assert set(pages) == {"https://x.edu/faculty", "https://x.edu/people/"}


def test_find_profile_clusters_groups_by_parent_path() -> None:
    xml_urls = re.findall(r"<loc>(.*?)</loc>", _xml("agnes_scott_urlset.xml"))
    directory_pages = set(find_directory_pages(xml_urls))

    clusters = find_profile_clusters(xml_urls, exclude=directory_pages)

    assert len(clusters) == 1
    (parent, members), = clusters.items()
    assert parent == "https://www.agnesscott.edu/directory/faculty/"
    assert len(members) == 27  # 28 directory/faculty urls in the fixture, minus the index


def test_find_profile_clusters_excludes_the_directory_index() -> None:
    urls = [
        "https://x.edu/directory/faculty/index.html",
        *[f"https://x.edu/directory/faculty/prof-{i}.html" for i in range(6)],
    ]
    directory_pages = set(find_directory_pages(urls))

    clusters = find_profile_clusters(urls, exclude=directory_pages)

    (members,) = clusters.values()
    assert "https://x.edu/directory/faculty/index.html" not in members
    assert len(members) == 6


def test_find_profile_clusters_below_minimum_size_is_ignored() -> None:
    urls = [f"https://x.edu/directory/faculty/prof-{i}.html" for i in range(3)]

    clusters = find_profile_clusters(urls)

    assert clusters == {}


def test_find_profile_clusters_ignores_unrelated_paths() -> None:
    """Five siblings under a path with no faculty/people/directory/staff hint
    is not a profile cluster — e.g. a news section."""
    urls = [f"https://x.edu/news/story-{i}.html" for i in range(6)]

    clusters = find_profile_clusters(urls)

    assert clusters == {}


def test_largest_profile_cluster_picks_the_biggest() -> None:
    clusters = {
        "https://x.edu/directory/staff/": [f"s{i}" for i in range(5)],
        "https://x.edu/directory/faculty/": [f"f{i}" for i in range(9)],
    }

    best = largest_profile_cluster(clusters)

    assert best == [f"f{i}" for i in range(9)]


def test_largest_profile_cluster_returns_none_when_empty() -> None:
    assert largest_profile_cluster({}) is None
