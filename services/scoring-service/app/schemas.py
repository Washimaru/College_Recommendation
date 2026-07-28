"""Pydantic mirror of docs/contracts/{profile,score}.schema.json.

Any change here MUST be mirrored in the contract JSON and the other service
mirrors (recommendation-service/app/schemas.py, gateway/src/types.ts), with a
version bump. Diverging is contract drift (H3).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = "1.0.0"

Size = Literal["small", "medium", "large"]
MBTI_PATTERN = r"^[EI][NS][TF][JP]$"


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_tuition: float | None = Field(default=None, ge=0)
    preferred_size: Size | None = None
    locations: list[str] = Field(default_factory=list)


class Weights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    academic: float | None = Field(default=None, ge=0)
    cost: float | None = Field(default=None, ge=0)
    fit: float | None = Field(default=None, ge=0)
    personality: float | None = Field(default=None, ge=0)


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gpa: float = Field(ge=0, le=4.0)
    sat: int | None = Field(default=None, ge=400, le=1600)
    mbti: str = Field(pattern=MBTI_PATTERN)
    intended_major: str = Field(min_length=1)
    preferences: Preferences = Field(default_factory=Preferences)
    weights: Weights | None = None


class University(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    avg_gpa: float = Field(ge=0, le=4.0)
    avg_sat: int = Field(ge=400, le=1600)
    acceptance_rate: float = Field(ge=0, le=1)
    tuition: float = Field(ge=0)
    size: Size
    location: str
    majors: list[str] = Field(default_factory=list)


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
