from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from faculty_pipeline.models import (
    Directory,
    Professor,
    RawProfile,
    School,
    StageSummary,
)


def test_school_round_trips_source_fields() -> None:
    school = School(
        school_id="mit",
        name="Massachusetts Institute of Technology",
        slug="massachusetts-institute-of-technology",
        country="US",
        state="MA",
        homepage="https://www.mit.edu",
        control="private",
        source_fields={"academics": {"foo": "bar"}},
    )

    assert school.source_fields["academics"]["foo"] == "bar"


def test_school_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        School(
            school_id="mit",
            name="MIT",
            slug="mit",
            country="US",
            homepage="https://www.mit.edu",
            unexpected="nope",
        )


def test_directory_confidence_bounds() -> None:
    with pytest.raises(ValidationError):
        Directory(
            school_id="mit",
            directory_urls=[],
            discovery_method="search+heuristic",
            robots_allowed=True,
            confidence=1.5,
        )


def test_raw_profile_requires_core_fields() -> None:
    profile = RawProfile(
        school_id="mit",
        profile_url="https://math.mit.edu/directory/profile?id=123",
        directory_url="https://math.mit.edu/directory/faculty/",
        html_cache_path="cache/html/deadbeef.html",
        fetched_at=datetime.now(UTC),
        http_status=200,
        parse_hint={"name": "Jane Doe", "title": "Professor"},
    )

    assert profile.http_status == 200


def test_professor_requires_name() -> None:
    with pytest.raises(ValidationError):
        Professor(
            school_id="mit",
            school_name="MIT",
            profile_url="https://math.mit.edu/p/1",
            directory_url="https://math.mit.edu/directory/",
            extraction_confidence=0.9,
            extracted_at=datetime.now(UTC),
        )


def test_stage_summary_defaults() -> None:
    summary = StageSummary(stage="load_filter", started_at=datetime.now(UTC))

    assert summary.processed == 0
    assert summary.skipped == 0
    assert summary.failed == 0
    assert summary.notes == []
