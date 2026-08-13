"""Pydantic mirror of docs/contracts/{profile,score,recommendation}.schema.json.

Independent mirror (each service owns its own). Keep in lockstep with the
contract JSON, scoring-service/app/schemas.py, and gateway/src/types.ts. A shape
change without a version bump across all mirrors is contract drift (H3).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = "8.0.0"

Size = Literal["small", "medium", "large"]
Scope = Literal["usa", "international", "both"]
StopReason = Literal["R1_converged", "R2_confident", "R3_no_change", "R4_iteration_cap"]
Provenance = Literal["observed", "web_verified", "editorial", "not_applicable", "absent"]

Region = Literal["Northeast", "South", "West", "Midwest", "International"]
Setting = Literal["urban", "suburban", "rural"]
InstitutionType = Literal["Public", "Private"]


class Program(BaseModel):
    """One 2-digit CIP family and the share of degrees awarded in it.

    Derived only from the federal PCIP columns, never from the editorial
    `majors` list: that list names a school's strengths, so absence from it is
    not evidence of anything. This is what lets a client say "awards no degrees
    in X" without inventing the claim.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    share: float = Field(ge=0, le=1)


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
    # Two-letter US state, if the student volunteers it. Used for one thing:
    # net_price at a public university is the federal average for in-state
    # students, so an out-of-state applicant owes the tuition gap on top of it
    # (scoring._cost_fit). Unstated changes nothing.
    home_state: str | None = Field(default=None, min_length=2, max_length=2)
    preferred_size: Size | None = None
    scope: Scope = "both"
    # Soft: fold into the `fit` dimension. An empty list means no preference.
    regions: list[Region] = Field(default_factory=list)
    settings: list[Setting] = Field(default_factory=list)
    # Hard: filters candidates before ranking, like scope.
    institution_type: InstitutionType | None = None


class Weights(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # A weight is a share of the rubric, so 1.0 is the ceiling. Scoring
    # normalises by the sum of the weights, so an unbounded value here would
    # make one dimension the entire score - {"cost": 999999} did exactly that.
    academic: float | None = Field(default=None, ge=0, le=1.0)
    cost: float | None = Field(default=None, ge=0, le=1.0)
    fit: float | None = Field(default=None, ge=0, le=1.0)
    culture: float | None = Field(default=None, ge=0, le=1.0)
    activities: float | None = Field(default=None, ge=0, le=1.0)
    personality: float | None = Field(default=None, ge=0, le=1.0)


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gpa: float = Field(ge=0, le=4.0)
    # Weighted GPA (0.0-5.0). Displayed only - never scored, never converted to
    # or from the unweighted `gpa` above. See docs/superpowers/specs/
    # 2026-08-03-gpa-scales-tiers-and-profiles-design.md decision 1.
    gpa_weighted: float | None = Field(default=None, ge=0, le=5.0)
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
    # Two-letter US state code. Structured on purpose: `location` is
    # display-only, so residency must never be decided by parsing it.
    state: str | None = Field(default=None, min_length=2, max_length=2)
    region: Region
    setting: Setting
    type: InstitutionType
    avg_gpa: float = Field(ge=0, le=4.0)
    avg_sat: int | None = Field(default=None, ge=400, le=1600)
    acceptance_rate: float | None = Field(default=None, ge=0, le=1)
    net_price: float | None = Field(default=None, ge=0)
    # Out-of-state, which is simply the price at a private school.
    sticker_tuition: float | None = Field(default=None, ge=0)
    # US only; not_applicable elsewhere. At most public schools this is
    # less than half of sticker_tuition.
    tuition_in_state: float | None = Field(default=None, ge=0)
    # None = unmeasured, [] = measured and awards none of these families.
    programs: list[Program] | None = None
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
    state: str | None = None
    region: Region
    setting: Setting
    type: InstitutionType
    avg_gpa: float = Field(ge=0, le=4.0)
    avg_sat: int | None = None
    acceptance_rate: float | None = None
    net_price: float | None = None
    # Both tuition figures travel with the summary: a match card shows what a
    # school costs, and for a public university the out-of-state price alone
    # is off by tens of thousands.
    sticker_tuition: float | None = None
    tuition_in_state: float | None = None
    programs: list[Program] | None = None
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
    admit_tier: Literal["extreme_reach", "reach", "target", "safety"] | None = None
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


class ClassifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    kind: ActivityKind = "other"
    description: str | None = Field(default=None, max_length=500)


class ClassifyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subjects: list[str]
