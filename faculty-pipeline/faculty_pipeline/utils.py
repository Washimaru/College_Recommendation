"""Small stateless helpers shared across stages and services."""
from __future__ import annotations

import hashlib
import re
import unicodedata


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
