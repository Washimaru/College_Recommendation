"""Small stateless helpers shared across stages and services."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from urllib.parse import urlsplit, urlunsplit

import tldextract
from selectolax.parser import HTMLParser

# Tags dropped outright before excerpting: pure boilerplate (nav/footer/
# header chrome repeats on every page of a site and drowns out the signal)
# or non-visible markup (script/style).
_NOISE_TAGS = ("script", "style", "noscript", "svg", "nav", "footer", "header")


def slugify(text: str) -> str:
    """Lowercase, ASCII, hyphen-separated slug.

    Used for `School.slug` (§4.1) and output filenames
    (`output/by_school/<slug>.csv`, §6 Stage 5).
    """
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    return normalized.strip("-")


def sha256_hex(value: str) -> str:
    """SHA-256 hex digest. Used as the HTML cache key for a URL (§5.2)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def extract_text_excerpt(html: str, max_chars: int) -> str:
    """Reduce a cached HTML page to a short, readable text excerpt used as
    evidence for `services.llm.classify_directory` (§6 Stage 2).

    What the model needs is a signal for "does this page list individual
    people, or departments, or nothing browsable" — link text and headings
    carry that signal far better than raw prose, so they're surfaced first
    and boilerplate nav/footer/header chrome is dropped outright. The result
    is capped at `max_chars` (paired with `config.llm_max_tokens` to bound
    token cost).

    Deterministic: the same HTML string always produces the same excerpt (no
    randomness, no wall-clock, no set-ordering of extracted text).
    """
    if not html or not html.strip():
        return ""

    tree = HTMLParser(html)
    for tag in _NOISE_TAGS:
        for node in tree.css(tag):
            node.decompose()

    headings = _collect_text(tree.css("h1, h2, h3, h4, h5, h6"))
    links = _collect_text(tree.css("a"))

    # Headings and links are pulled out above; remove them from the tree
    # before taking the leftover body text so that text isn't duplicated
    # between the "Headings"/"Links" lines and the "Text" line.
    for node in tree.css("h1, h2, h3, h4, h5, h6, a"):
        node.decompose()
    body_node = tree.body if tree.body is not None else tree.root
    body_text = _clean_whitespace(body_node.text(separator=" ")) if body_node is not None else ""

    parts: list[str] = []
    if headings:
        parts.append("Headings: " + " | ".join(headings))
    if links:
        parts.append("Links: " + " | ".join(links))
    if body_text:
        parts.append("Text: " + body_text)

    return "\n".join(parts)[:max_chars]


def _collect_text(nodes: list) -> list[str]:
    """Cleaned, order-preserving, de-duplicated text of each node."""
    seen: set[str] = set()
    out: list[str] = []
    for node in nodes:
        text = _clean_whitespace(node.text(separator=" "))
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _clean_whitespace(text: str) -> str:
    return " ".join(text.split())


# --------------------------------------------------------------------------
# URL helpers — Stage 3 (crawl.py) link enumeration.
#
# `suffix_list_urls=()` pins tldextract to its bundled public-suffix-list
# snapshot instead of fetching a live one, which would be a second,
# undeclared network path outside `services/http_client.py` and would make
# domain classification non-deterministic across environments/offline runs.
# --------------------------------------------------------------------------

_TLD_EXTRACTOR = tldextract.TLDExtract(suffix_list_urls=())


def normalize_url(url: str) -> str:
    """Canonical form of `url` for de-duplication (§6 Stage 3): fragment
    stripped, trailing-slash variants collapsed to one form, scheme/host
    lowercased. Query strings are preserved (they can be load-bearing, e.g.
    `?id=123`). Caller is responsible for resolving relative URLs against
    their page's base URL first (`urllib.parse.urljoin`) — this function only
    canonicalizes an already-absolute URL.
    """
    parsed = urlsplit(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def registrable_domain(url: str) -> str:
    """The registrable ("eTLD+1") domain of `url`, e.g. both
    `https://www.bard.edu/faculty` and `https://math.bard.edu/people` return
    `bard.edu`. Used by Stage 3's same-domain check (§6 Stage 3 / the M4
    same-domain requirement) so a link off to an aggregator or social network
    (different registrable domain) is rejected while department subdomains of
    the same university are not.
    """
    return _TLD_EXTRACTOR(url).top_domain_under_public_suffix.lower()


# --------------------------------------------------------------------------
# Alphabetical-partial-capture detection — shared by Stage 3 (crawl.py,
# where it first catches a JS-rendered A-Z directory that only server-
# rendered its first section) and Stage 5 (export.py, which re-checks the
# *final* set of profile URLs that actually made it into a school's CSV, so
# a partial capture is flagged even if it slipped past crawl-time detection
# — e.g. a `--limit`/`--school` partial run, or profiles dropped later by
# extract's confidence filter in a way that happens to concentrate the
# survivors on one letter). One implementation, two call sites, so the
# definition of "looks partial" can't drift between them.
# --------------------------------------------------------------------------

# Below this many profiles, an initial-concentration reading is noise: a small
# department genuinely can have four people whose names all start with A.
PARTIAL_MIN_PROFILES = 8
PARTIAL_CONCENTRATION = 0.9


def looks_alphabetically_partial(profile_urls: list[str]) -> bool:
    """True when the captured profiles all sit under one letter of the alphabet.

    The failure this catches is silent and expensive. An A-Z directory that
    server-renders only its first section, loading B-Z by script on click, hands
    the crawler a page full of real, valid profile links — so nothing errors,
    nothing 404s, and the run reports success having collected perhaps 4% of the
    faculty. Zero links trips the existing `needs_dynamic_render` check; 17 of
    400 does not, and reads as a complete result all the way into the CSV.

    Real faculty lists spread across the alphabet. A large set sharing a single
    initial means the crawler saw one slice of a paginated directory, not a
    small school. Both name orders are checked, since profile slugs appear as
    `susan-aberth` and as `aberth-susan` depending on the site.
    """
    if len(profile_urls) < PARTIAL_MIN_PROFILES:
        return False

    slugs = [urlsplit(u).path.rstrip("/").rsplit("/", 1)[-1].lower() for u in profile_urls]
    tokenised = [[t for t in s.split("-") if t and t[0].isalpha()] for s in slugs]
    tokenised = [t for t in tokenised if len(t) >= 2]
    if len(tokenised) < PARTIAL_MIN_PROFILES:
        return False

    # Surnames are compound often enough that a single token position is not
    # enough: `ziad-abu-rish` ends in "rish" but is filed under A. So for each
    # naming convention — given-name first, or surname first — take the set of
    # initials across the *surname side* of each slug, and ask whether one
    # letter appears in nearly all of them.
    for drop in ("first", "last"):
        per_slug_initials = [
            {t[0] for t in (tokens[1:] if drop == "first" else tokens[:-1])} for tokens in tokenised
        ]
        counts = Counter(letter for initials in per_slug_initials for letter in initials)
        if not counts:
            continue
        if max(counts.values()) / len(per_slug_initials) >= PARTIAL_CONCENTRATION:
            return True
    return False


# --------------------------------------------------------------------------
# Faculty vs staff
# --------------------------------------------------------------------------

# The first live run exported ArtCenter's vice-presidents as professors: the
# crawl found them because that school's sitemap mixes staff into `/people/`,
# and nothing downstream ever asked whether the person teaches. The title is
# the only evidence available for that question on a profile page.
#
# Ordered deliberately: an academic rank wins outright, because plenty of real
# professors also hold an administrative post ("Dean of the Faculty and
# Professor of Biology"). Only a clear administrative title with no academic
# rank in it is called staff, and anything unrecognised stays unknown rather
# than being guessed — dropping a real professor is the worse error.
_ACADEMIC_TITLE_RE = re.compile(
    r"\b("
    r"professor|prof\.|lecturer|instructor|faculty|preceptor|"
    r"artist[- ]in[- ]residence|writer[- ]in[- ]residence|scholar[- ]in[- ]residence|"
    r"postdoc(?:toral)?|research (?:scientist|professor)|teaching (?:fellow|associate)"
    r")\b",
    re.IGNORECASE,
)

# "Emeritus" on its own is an honour, not an appointment: the first version of
# this classifier read "Philanthropist; ArtCenter Trustee Emeritus" and called
# her faculty. It only counts attached to an academic word, which the pattern
# above already matches on its own ("Professor Emeritus", "Emeritus Faculty").

_ADMIN_TITLE_RE = re.compile(
    r"\b("
    r"president|provost|chancellor|registrar|bursar|treasurer|trustee|"
    r"chief \w+ officer|vice[- ]chancellor|"
    r"director of (?:admissions?|communications?|marketing|development|advancement|"
    r"human resources|finance|operations|athletics|facilities|alumni relations)|"
    r"(?:head |assistant |associate )?coach|"
    r"administrative (?:assistant|coordinator)|"
    r"admissions (?:counselor|officer)|"
    r"human resources|"
    # ArtCenter publishes trustees, alumni and corporate advisers in the same
    # /people/ tree as its faculty, so these titles are what a crawl of that
    # school actually returns. An academic rank still wins over all of them.
    r"board (?:of trustees|chair|member)|member, board|"
    r"alumn(?:us|a|i|ae)|philanthropist|"
    r"chief|founder|executive director|"
    r"(?:design |managing )?principal, "
    r")\b",
    re.IGNORECASE,
)


def classify_role(title: str | None) -> bool | None:
    """Does this title describe teaching faculty?

    `True` for an academic appointment, `False` for a clear administrative or
    support role, and `None` when the title says neither — including when
    there is no title at all. `None` means "keep it, unclassified"; only
    `False` is treated as grounds to leave a row out of the CSVs.
    """
    if not title or not title.strip():
        return None
    if _ACADEMIC_TITLE_RE.search(title):
        return True
    if _ADMIN_TITLE_RE.search(title):
        return False
    return None
