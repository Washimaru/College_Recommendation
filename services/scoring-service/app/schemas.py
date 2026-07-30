"""Pydantic mirror of docs/contracts/{profile,score}.schema.json.

Any change here MUST be mirrored in the contract JSON and the other service
mirrors (recommendation-service/app/schemas.py, gateway/src/types.ts), with a
version bump. Diverging is contract drift (H3).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = "3.1.0"

Size = Literal["small", "medium", "large"]
# Country scope. A hard filter on which schools are considered at all.
Scope = Literal["usa", "international", "both"]
Provenance = Literal["observed", "web_verified", "editorial", "not_applicable", "absent"]

# The six bipolar culture axes, shared by Profile.culture_prefs and
# University.culture. 0.0 and 1.0 are opposite poles; 0.5 means indifferent.
CULTURE_AXES = ("collab", "quirky", "idealist", "research", "spirit", "seminar")


class CulturePrefs(BaseModel):
    """Self-reported preference per axis. Defaults centre on 0.5 so an untouched
    slider expresses no preference and contributes nothing to the score."""

    model_config = ConfigDict(extra="forbid")

    collab: float = Field(default=0.5, ge=0, le=1)
    quirky: float = Field(default=0.5, ge=0, le=1)
    idealist: float = Field(default=0.5, ge=0, le=1)
    research: float = Field(default=0.5, ge=0, le=1)
    spirit: float = Field(default=0.5, ge=0, le=1)
    seminar: float = Field(default=0.5, ge=0, le=1)


class Culture(BaseModel):
    """A university's position on the same six axes. Required, not optional."""

    model_config = ConfigDict(extra="forbid")

    collab: float = Field(ge=0, le=1)
    quirky: float = Field(ge=0, le=1)
    idealist: float = Field(ge=0, le=1)
    research: float = Field(ge=0, le=1)
    spirit: float = Field(ge=0, le=1)
    seminar: float = Field(ge=0, le=1)


ActivityKind = Literal[
    "competition", "club", "volunteering", "work", "sport", "arts", "research", "other"
]


class Activity(BaseModel):
    """Something the student does. Free text plus a coarse kind, matched by
    keyword against what a school is strong in."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    kind: ActivityKind = "other"
    years: int | None = Field(default=None, ge=0, le=12)


class Personality(BaseModel):
    """Derived from the questionnaire, on axes the culture vector does not
    cover, so no signal is scored twice. 0.5 means no preference."""

    model_config = ConfigDict(extra="forbid")

    # 0 = steady and low-pressure, 1 = driven and highly competitive
    intensity: float = Field(default=0.5, ge=0, le=1)
    # 0 = small and close-knit, 1 = large and bustling
    scale: float = Field(default=0.5, ge=0, le=1)


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_tuition: float | None = Field(default=None, ge=0)
    preferred_size: Size | None = None
    locations: list[str] = Field(default_factory=list)
    scope: Scope = "both"


class Weights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    academic: float | None = Field(default=None, ge=0)
    cost: float | None = Field(default=None, ge=0)
    fit: float | None = Field(default=None, ge=0)
    culture: float | None = Field(default=None, ge=0)
    activities: float | None = Field(default=None, ge=0)
    personality: float | None = Field(default=None, ge=0)


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gpa: float = Field(ge=0, le=4.0)
    sat: int | None = Field(default=None, ge=400, le=1600)
    intended_major: str = Field(min_length=1)
    culture_prefs: CulturePrefs = Field(default_factory=CulturePrefs)
    personality: Personality = Field(default_factory=Personality)
    activities: list[Activity] = Field(default_factory=list)
    preferences: Preferences = Field(default_factory=Preferences)
    weights: Weights | None = None


class University(BaseModel):
    """Nullable admissions fields are deliberate: a missing value is null, never
    back-derived. `provenance` records where each value came from."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    unitid: str | None = None
    name: str = Field(min_length=1)
    country: str = Field(min_length=1)
    location: str
    avg_gpa: float = Field(ge=0, le=4.0)
    avg_sat: int | None = Field(default=None, ge=400, le=1600)
    acceptance_rate: float | None = Field(default=None, ge=0, le=1)
    net_price: float | None = Field(default=None, ge=0)
    sticker_tuition: float | None = Field(default=None, ge=0)
    enrollment: int | None = Field(default=None, ge=0)
    size: Size
    majors: list[str] = Field(default_factory=list)
    culture: Culture
    details: dict | None = None
    provenance: dict[str, Provenance] = Field(default_factory=dict)


class RankRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: Profile
    weight_feedback: dict[str, float] = Field(default_factory=dict)
    universities: list[University] = Field(default_factory=list)


class ScoredUniversity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    university_id: str
    score: float = Field(ge=0, le=1)
    components: dict[str, float]


class RankResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scores: list[ScoredUniversity]
