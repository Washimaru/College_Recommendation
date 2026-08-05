"""Pydantic v2 models for the §4 data schemas.

`School` / `Directory` / `RawProfile` / `Professor` mirror the JSONL records
written by stages 1-4 (docs/FACULTY_PIPELINE.md §4); `StageSummary` is the
return type every stage's `run()` produces (§5.7).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------
# §4.1 School record — data/schools.jsonl
# --------------------------------------------------------------------------


class School(BaseModel):
    """A normalized U.S. school record, output by Stage 1 (load_filter)."""

    model_config = ConfigDict(extra="forbid")

    school_id: str
    name: str
    slug: str
    country: str
    state: str | None = None
    homepage: str
    control: str | None = None
    source_fields: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------
# §4.2 Directory record — data/directories.jsonl
# --------------------------------------------------------------------------


class Directory(BaseModel):
    """A school's discovered official faculty-directory URL(s), output by
    Stage 2 (discover)."""

    model_config = ConfigDict(extra="forbid")

    school_id: str
    directory_urls: list[str] = Field(default_factory=list)
    discovery_method: str
    robots_allowed: bool
    confidence: float = Field(ge=0, le=1)
    notes: str | None = None


# --------------------------------------------------------------------------
# §4.3 Raw profile record — data/profiles_raw.jsonl
# --------------------------------------------------------------------------


class RawProfile(BaseModel):
    """A fetched professor-profile page, before extraction. Output by
    Stage 3 (crawl)."""

    model_config = ConfigDict(extra="forbid")

    school_id: str
    profile_url: str
    directory_url: str
    html_cache_path: str
    fetched_at: datetime
    http_status: int
    parse_hint: dict[str, str | None] = Field(default_factory=dict)


# --------------------------------------------------------------------------
# §4.4 Clean professor record — data/profiles_clean.jsonl and CSV columns
# --------------------------------------------------------------------------


class Professor(BaseModel):
    """A validated, LLM-normalized professor record. Output by Stage 4
    (extract) and the row shape for Stage 5's CSVs (§4.4 table); field order
    here is the CSV column order."""

    model_config = ConfigDict(extra="forbid")

    school_id: str
    school_name: str
    professor_name: str
    title: str | None = None
    department: str | None = None
    email: str | None = None
    phone: str | None = None
    research_interests: str | None = None  # semicolon-separated
    profile_url: str
    directory_url: str
    extraction_confidence: float = Field(ge=0, le=1)
    extracted_at: datetime


# --------------------------------------------------------------------------
# §5.8 Stage summary — the return type of every stage's run()
# --------------------------------------------------------------------------


class StageSummary(BaseModel):
    """Counts of processed / skipped / failed items for one stage run,
    printed at the end of every stage (§6, §8)."""

    model_config = ConfigDict(extra="forbid")

    stage: str
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    started_at: datetime
    finished_at: datetime | None = None
    notes: list[str] = Field(default_factory=list)
