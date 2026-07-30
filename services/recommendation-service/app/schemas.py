"""Pydantic mirror of docs/contracts/{profile,score,recommendation}.schema.json.

Independent mirror (each service owns its own). Keep in lockstep with the
contract JSON, scoring-service/app/schemas.py, and gateway/src/types.ts. A shape
change without a version bump across all mirrors is contract drift (H3).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = "4.0.0"

Size = Literal["small", "medium", "large"]
Scope = Literal["usa", "international", "both"]
StopReason = Literal["R1_converged", "R2_confident", "R3_no_change", "R4_iteration_cap"]
Provenance = Literal["observed", "web_verified", "editorial", "not_applicable", "absent"]

Region = Literal["Northeast", "South", "West", "Midwest", "International"]
Setting = Literal["urban", "suburban", "rural"]
InstitutionType = Literal["Public", "Private"]


class Population(BaseModel):
    """Student-body composition. Absent for non-US schools."""

    model_config = ConfigDict(extra="forbid")

    international_share: float | None = Field(default=None, ge=0, le=1)
    women_share: float | None = Field(default=None, ge=0, le=1)
    first_gen_share: float | None = Field(default=None, ge=0, le=1)

# Six bipolar culture axes. 0.0/1.0 are opposite poles; 0.5 means indifferent.
CULTURE_AXES = ("collab", "quirky", "idealist", "research", "spirit", "seminar")


class CulturePrefs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    collab: float = Field(default=0.5, ge=0, le=1)
    quirky: float = Field(default=0.5, ge=0, le=1)
    idealist: float = Field(default=0.5, ge=0, le=1)
    research: float = Field(default=0.5, ge=0, le=1)
    spirit: float = Field(default=0.5, ge=0, le=1)
    seminar: float = Field(default=0.5, ge=0, le=1)


class Culture(BaseModel):
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
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    kind: ActivityKind = "other"
    years: int | None = Field(default=None, ge=0, le=12)
    description: str | None = Field(default=None, max_length=500)


class Personality(BaseModel):
    """Axes the culture vector does not cover, so no signal is scored twice."""

    model_config = ConfigDict(extra="forbid")
    intensity: float = Field(default=0.5, ge=0, le=1)
    scale: float = Field(default=0.5, ge=0, le=1)


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_tuition: float | None = Field(default=None, ge=0)
    preferred_size: Size | None = None
    scope: Scope = "both"
    # Soft: fold into the `fit` dimension. An empty list means no preference.
    regions: list[Region] = Field(default_factory=list)
    settings: list[Setting] = Field(default_factory=list)
    # Hard: filters candidates before ranking, like scope.
    institution_type: InstitutionType | None = None


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
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1)
    unitid: str | None = None
    name: str = Field(min_length=1)
    country: str = Field(min_length=1)
    location: str
    region: Region
    setting: Setting
    type: InstitutionType
    avg_gpa: float = Field(ge=0, le=4.0)
    avg_sat: int | None = Field(default=None, ge=400, le=1600)
    acceptance_rate: float | None = Field(default=None, ge=0, le=1)
    net_price: float | None = Field(default=None, ge=0)
    sticker_tuition: float | None = Field(default=None, ge=0)
    enrollment: int | None = Field(default=None, ge=0)
    size: Size
    majors: list[str] = Field(default_factory=list)
    culture: Culture
    population: Population | None = None
    url: str | None = None
    net_price_calculator_url: str | None = None
    details: dict | None = None
    provenance: dict[str, Provenance] = Field(default_factory=dict)


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


class UniversitySummary(BaseModel):
    """Compact view of a university, carried on each Result so the client can
    show why a school is on the list and how trustworthy each figure is."""

    model_config = ConfigDict(extra="forbid")
    country: str
    location: str
    region: Region
    setting: Setting
    type: InstitutionType
    avg_gpa: float = Field(ge=0, le=4.0)
    avg_sat: int | None = None
    acceptance_rate: float | None = None
    net_price: float | None = None
    enrollment: int | None = None
    size: Size
    majors: list[str] = Field(default_factory=list)
    culture: Culture
    population: Population | None = None
    url: str | None = None
    net_price_calculator_url: str | None = None
    details: dict | None = None
    provenance: dict[str, Provenance] = Field(default_factory=dict)


class Result(BaseModel):
    model_config = ConfigDict(extra="forbid")
    university_id: str
    name: str
    score: float = Field(ge=0, le=1)
    rationale: str
    admit_tier: Literal["reach", "target", "safety"] | None = None
    university: UniversitySummary


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
