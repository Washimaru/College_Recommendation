"""Pydantic mirror of docs/contracts/{profile,score,recommendation}.schema.json.

Independent mirror (each service owns its own). Keep in lockstep with the
contract JSON, scoring-service/app/schemas.py, and gateway/src/types.ts. A shape
change without a version bump across all mirrors is contract drift (H3).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = "1.0.0"

Size = Literal["small", "medium", "large"]
StopReason = Literal["R1_converged", "R2_confident", "R3_no_change", "R4_iteration_cap"]
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


class ScoredUniversity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    university_id: str
    score: float = Field(ge=0, le=1)
    components: dict[str, float]


class RecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: Profile
    max_iterations: int = Field(default=5, ge=1, le=20)
    top_k: int = Field(default=5, ge=1, le=50)


class Result(BaseModel):
    model_config = ConfigDict(extra="forbid")
    university_id: str
    name: str
    score: float = Field(ge=0, le=1)
    rationale: str


class TraceStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    iteration: int = Field(ge=0)
    top_ids: list[str]
    confidence: float = Field(ge=0, le=1)
    stop_reason: str | None = None


class RecommendationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    results: list[Result]
    confidence: float = Field(ge=0, le=1)
    stop_reason: StopReason
    trace: list[TraceStep]
