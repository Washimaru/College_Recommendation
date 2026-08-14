"""Pydantic mirror of docs/contracts/{profile,score}.schema.json.

Any change here MUST be mirrored in the contract JSON and the other service
mirrors (recommendation-service/app/schemas.py, gateway/src/types.ts), with a
version bump. Diverging is contract drift (H3).
"""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = "11.0.0"

# One multiplicative adjustment to a weight. The recommendation loop clamps
# these to [0.5, 1.5] before sending them; the same range is enforced here
# because this service is deployed on its own port and answers whoever calls it.
WeightFactor = Annotated[float, Field(ge=0.5, le=1.5)]

Size = Literal["small", "medium", "large"]
# Country scope. A hard filter on which schools are considered at all.
Scope = Literal["usa", "international", "both"]
Provenance = Literal["observed", "web_verified", "editorial", "not_applicable", "absent"]

Region = Literal["Northeast", "South", "West", "Midwest", "International"]
Setting = Literal["urban", "suburban", "rural"]
InstitutionType = Literal["Public", "Private"]


class ActiveResearcher(BaseModel):
    """Someone publishing from this school now, and what they work on.

    Counted from publication records, so it says nothing about a teaching
    appointment: it misses faculty who do not publish, and includes some
    research staff. That is why the field is not called `professors`.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    research: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)
    recent_works: int | None = Field(default=None, ge=0)
    last_active: int | None = None
    # How much of their work others build on, and what they have been
    # recognised for. Together these decide who leads the list.
    h_index: int | None = Field(default=None, ge=0)
    awards: list[str] = Field(default_factory=list)
    source: Literal["openalex", "directory"]
    source_url: str = Field(min_length=1)


class NotableProfessor(BaseModel):
    """A named professor, from Wikipedia category membership plus Wikidata.

    Carries who someone is and where to check it — never an email or a phone
    number. That line is what keeps the faculty CSVs gitignored while this
    field is publishable: a professor's employer is not private, their inbox
    is. No model is involved in producing these, so a name here belongs to
    someone who exists.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    known_for: str | None = None
    fields: list[str] = Field(default_factory=list)
    # "historical" means a recorded date of death. Its absence is not proof of
    # tenure, which is why these are not "alive" and "dead".
    status: Literal["current", "historical"]
    prominence: int = Field(default=0, ge=0)
    # Named honours from Wikidata (P166).
    awards: list[str] = Field(default_factory=list)
    source: Literal["wikipedia", "directory"]
    source_url: str = Field(min_length=1)


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
    description: str | None = Field(default=None, max_length=500)


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
    """Nullable admissions fields are deliberate: a missing value is null, never
    back-derived. `provenance` records where each value came from."""

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
    # None = nobody searched; [] = searched and found nobody, which is a real
    # answer for a small college.
    notable_faculty: list[NotableProfessor] | None = None
    active_faculty: list[ActiveResearcher] | None = None
    enrollment: int | None = Field(default=None, ge=0)
    size: Size
    majors: list[str] = Field(default_factory=list)
    culture: Culture
    population: Population | None = None
    url: str | None = None
    net_price_calculator_url: str | None = None
    details: dict | None = None
    provenance: dict[str, Provenance] = Field(default_factory=dict)


class RankRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: Profile
    # Clamped by the recommendation loop, and enforced again here: this
    # service is deployed on its own port, so the clamp cannot rely on the
    # caller having applied it.
    weight_feedback: dict[str, WeightFactor] = Field(default_factory=dict)
    universities: list[University] = Field(default_factory=list)


class ScoredUniversity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    university_id: str
    score: float = Field(ge=0, le=1)
    components: dict[str, float]


class RankResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scores: list[ScoredUniversity]


class ClassifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    kind: ActivityKind = "other"
    description: str | None = Field(default=None, max_length=500)


class ClassifyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subjects: list[str]
