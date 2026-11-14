"""Request and response schemas for the iso-topos REST API (ER-4)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from isotopos.core.models import (
    PhysicalFilter,
    PlanetaryBody,
    ScoringMode,
    TargetLocation,
)

ExportFormat = Literal["csv", "json"]


class TargetExtractRequest(BaseModel):
    """Request body for extracting a preset or arbitrary Moon/Mars coordinate."""

    preset_id: str | None = None
    body: PlanetaryBody | None = None
    lat: float | None = Field(default=None, ge=-90.0, le=90.0)
    lon: float | None = Field(default=None, ge=-180.0, le=360.0)


class RankRequest(BaseModel):
    """Request body for ranking Earth H3 cells and Hotspots."""

    target: TargetLocation
    weights: dict[str, float] | None = None
    mode: ScoringMode = ScoringMode.CLAMPED
    filters: list[PhysicalFilter] = Field(default_factory=list)
    exclude_well_known: bool = False
    top_k: int = Field(default=15, ge=1, le=100)
    dimension_id: str | None = None


class SiteInspectRequest(BaseModel):
    """Request body for inspecting any single Earth H3 cell or hotspot."""

    target: TargetLocation
    weights: dict[str, float] | None = None
    mode: ScoringMode = ScoringMode.CLAMPED


class WeightEvaluateRequest(BaseModel):
    """Request body for evaluating parameter weights from a textual mission description."""

    mission_description: str = Field(min_length=3, max_length=4000)
