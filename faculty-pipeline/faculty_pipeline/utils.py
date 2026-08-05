"""Small stateless helpers shared across stages and services."""
from __future__ import annotations

import hashlib
import re
import unicodedata

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
