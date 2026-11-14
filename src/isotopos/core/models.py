"""Domain models for iso-topos spatial sites, targets, provenance, and scoring results."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class PlanetaryBody(str, Enum):
    """Supported planetary target bodies."""

    MOON = "moon"
    MARS = "mars"


class ScoringMode(str, Enum):
    """Scoring behavior when target values exceed Earth's physical envelope."""

    CLAMPED = "clamped"
    STRICT = "strict"


class ProvenanceMetadata(BaseModel):
    """Dataset citation and resolution metadata required by DR-3."""

    agency_mission: str
    dataset_name: str
    url: str
    unit: str
    resolution: str


class DimensionSpec(BaseModel):
    """Declarative analogy dimension specification (FR-7, FR-8, FR-9)."""

    id: str
    name: str
    description: str
    is_core_v1: bool = True


class ParameterSpec(BaseModel):
    """Declarative physical parameter specification (FR-7, DR-3)."""

    id: str
    dimension_id: str
    label: str
    unit: str
    earth_min: float
    earth_max: float
    default_weight: float = Field(default=1.0, ge=0.0, le=1.0)
    description: str = ""
    earth_provenance: ProvenanceMetadata
    moon_provenance: ProvenanceMetadata
    mars_provenance: ProvenanceMetadata

    @model_validator(mode="after")
    def _validate_bounds(self) -> ParameterSpec:
        if self.earth_max <= self.earth_min:
            raise ValueError(f"Parameter {self.id}: earth_max must exceed earth_min")
        return self

    @property
    def span(self) -> float:
        """Physical normalization span across Earth bounds."""
        return self.earth_max - self.earth_min


class TargetLocation(BaseModel):
    """A planetary target parameter vector (from preset, coordinate extraction, or manual override)."""

    name: str
    body: PlanetaryBody
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=360.0)
    parameters: dict[str, float]
    is_extrapolated: bool = False
    extrapolated_parameters: list[str] = Field(default_factory=list)
    notes: str = ""


class TargetPreset(TargetLocation):
    """Curated Moon or Mars mission/landing target preset (FR-2)."""

    id: str
    mission_context: str
    recommended_weights: dict[str, float] = Field(default_factory=dict)
    exploration_focus: list[str] = Field(default_factory=list)


class EarthSite(BaseModel):
    """A terrestrial spatial cell (H3) or high-resolution local hotspot (FR-4, FR-5, FR-6)."""

    id: str
    name: str
    region: str
    site_type: Literal["h3_cell", "hotspot"]
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    is_well_known: bool = False
    feature_category: str = "grid_cell"
    parameters: dict[str, float]
    notes: str = ""


class PhysicalFilter(BaseModel):
    """Physical range filter on any registered parameter (FR-15)."""

    parameter_id: str
    min_value: float | None = None
    max_value: float | None = None


class ParameterComparison(BaseModel):
    """Unit-level Earth vs. planetary target comparison for a single parameter (FR-11, FR-15)."""

    parameter_id: str
    label: str
    dimension_id: str
    unit: str
    earth_value: float
    target_value: float
    effective_target_value: float
    delta: float
    out_of_envelope_delta: float = 0.0
    similarity: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0, le=1.0)


class DimensionBreakdown(BaseModel):
    """Per-dimension sub-score and match status (FR-10, FR-11)."""

    dimension_id: str
    dimension_name: str
    sub_score: float | None = None  # None represents N/A when all params in dimension have weight 0
    active_parameter_count: int = 0
    status: Literal["strong", "moderate", "divergent", "N/A"]


class EarthLimitCaveat(BaseModel):
    """Explicit scientific caveat where terrestrial analogs break down (FR-11)."""

    category: str
    title: str
    explanation: str


class RankedAnalogResult(BaseModel):
    """Complete ranked analog evaluation and divergence explanation for an Earth site."""

    site: EarthSite
    overall_score: float = Field(ge=0.0, le=1.0)
    dimension_breakdowns: list[DimensionBreakdown]
    parameter_comparisons: list[ParameterComparison]
    strongest_dimensions: list[str]
    diverging_dimensions: list[str]
    earth_limit_caveats: list[EarthLimitCaveat]
    exploration_relevance: list[str]
