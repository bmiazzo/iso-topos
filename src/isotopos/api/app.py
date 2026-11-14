"""FastAPI application factory and REST endpoints (FR-1..FR-15, DR-2, DR-3, NFR-1, DEC-005)."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from isotopos.core.models import (
    EarthSite,
    PhysicalFilter,
    PlanetaryBody,
    ScoringMode,
    TargetLocation,
    TargetPreset,
)
from isotopos.core.registry import DEFAULT_REGISTRY
from isotopos.etl.catalog_data import EARTH_HOTSPOTS, PLANETARY_PRESETS
from isotopos.etl.interpolator import PlanetaryGridInterpolator
from isotopos.etl.spatial_builder import build_earth_h3_grid, build_planetary_grid
from isotopos.scoring.engine import AnalogScoringEngine, PrepackedSiteIndex
from isotopos.scoring.llm_client import LLMClient, LLMConfigurationError, LLMProviderError
from isotopos.scoring.mission_weights import evaluate_mission_weights


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


class DataStore:
    """In-memory pre-loaded spatial index and pre-packed NumPy matrix container."""

    def __init__(self, data_dir: Path | None = None) -> None:
        root = Path(__file__).resolve().parents[3]
        processed = data_dir or (root / "data" / "processed")

        if (processed / "earth_h3_sites.json").exists():
            raw_sites = json.loads((processed / "earth_h3_sites.json").read_text(encoding="utf-8"))
            self.h3_sites = [EarthSite.model_construct(**s) for s in raw_sites]
            self.earth_geojson = json.loads(
                (processed / "earth_h3_grid.geojson").read_text(encoding="utf-8")
            )
            raw_hotspots = json.loads((processed / "earth_hotspots.json").read_text(encoding="utf-8"))
            self.hotspots = [EarthSite(**h) for h in raw_hotspots]
            raw_presets = json.loads(
                (processed / "planetary_presets.json").read_text(encoding="utf-8")
            )
            self.presets = [TargetPreset(**p) for p in raw_presets]
            moon_grid = json.loads((processed / "moon_grid.json").read_text(encoding="utf-8"))
            mars_grid = json.loads((processed / "mars_grid.json").read_text(encoding="utf-8"))
        else:
            self.h3_sites, self.earth_geojson = build_earth_h3_grid(max_cells=500)
            self.hotspots = list(EARTH_HOTSPOTS)
            self.presets = list(PLANETARY_PRESETS)
            moon_grid = build_planetary_grid(PlanetaryBody.MOON, step_deg=10.0)
            mars_grid = build_planetary_grid(PlanetaryBody.MARS, step_deg=10.0)

        self.h3_prepacked = PrepackedSiteIndex.from_sites(self.h3_sites, DEFAULT_REGISTRY)
        self.hotspot_prepacked = PrepackedSiteIndex.from_sites(self.hotspots, DEFAULT_REGISTRY)

        self.interpolator = PlanetaryGridInterpolator(
            registry=DEFAULT_REGISTRY,
            presets=self.presets,
            moon_grid=moon_grid,
            mars_grid=mars_grid,
        )
        self.engine = AnalogScoringEngine(DEFAULT_REGISTRY)


def create_app(
    data_dir: Path | None = None,
    llm_client: LLMClient | None = None,
) -> FastAPI:
    """Create and configure the iso-topos FastAPI application."""
    application = FastAPI(
        title="iso-topos API",
        description="Planetary-to-Earth Analog Discovery & Characterization Engine",
        version="0.2.0",
    )
    application.add_middleware(GZipMiddleware, minimum_size=1000)

    store = DataStore(data_dir=data_dir)
    static_dir = Path(__file__).resolve().parent.parent / "static"

    if static_dir.exists():
        application.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @application.get("/", include_in_schema=False)
    def serve_index() -> Any:
        index_path = static_dir / "index.html"
        if index_path.exists():
            return FileResponse(index_path)
        return {"service": "iso-topos", "status": "ok"}

    @application.get("/api/v1/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "h3_cell_count": len(store.h3_sites),
            "hotspot_count": len(store.hotspots),
            "preset_count": len(store.presets),
        }

    @application.get("/api/v1/metadata")
    def get_metadata() -> dict[str, Any]:
        return {
            "dimensions": [d.model_dump() for d in DEFAULT_REGISTRY.dimensions],
            "parameters": [p.model_dump() for p in DEFAULT_REGISTRY.parameters],
            "presets": [p.model_dump() for p in store.presets],
            "hotspots": [h.model_dump() for h in store.hotspots],
        }

    @application.get("/api/v1/earth-grid")
    def get_earth_grid() -> JSONResponse:
        return JSONResponse(content=store.earth_geojson)

    @application.get("/api/v1/earth-grid/parameter/{param_id}")
    def get_earth_grid_parameter(param_id: str) -> dict[str, Any]:
        if param_id not in store.h3_prepacked.param_col_index:
            raise HTTPException(status_code=404, detail=f"Unknown parameter_id '{param_id}'")
        return {
            "parameter_id": param_id,
            "values": store.h3_prepacked.get_parameter_map(param_id),
        }

    @application.post("/api/v1/target/extract")
    def extract_target(req: TargetExtractRequest) -> dict[str, Any]:
        if req.preset_id:
            try:
                return store.interpolator.extract_preset(req.preset_id).model_dump()
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

        if req.body is not None and req.lat is not None and req.lon is not None:
            return store.interpolator.extract_coordinate(
                body=req.body,
                lat=req.lat,
                lon=req.lon,
            ).model_dump()

        raise HTTPException(
            status_code=400,
            detail="Provide either 'preset_id' or ('body', 'lat', 'lon').",
        )

    @application.post("/api/v1/rank")
    def rank_analogs(req: RankRequest) -> dict[str, Any]:
        h3_eval = store.engine.evaluate_prepacked(
            prepacked=store.h3_prepacked,
            target=req.target,
            weights=req.weights,
            mode=req.mode,
            filters=req.filters,
            exclude_well_known=req.exclude_well_known,
            top_k=req.top_k,
            include_dimension_scores=req.dimension_id is not None,
            dimension_id=req.dimension_id,
        )
        hotspot_eval = store.engine.evaluate_prepacked(
            prepacked=store.hotspot_prepacked,
            target=req.target,
            weights=req.weights,
            mode=req.mode,
            filters=req.filters,
            exclude_well_known=req.exclude_well_known,
            top_k=None,
            include_dimension_scores=False,
        )
        return {
            "all_weights_zero": h3_eval.all_weights_zero,
            "total_h3_evaluated": h3_eval.total_candidates_evaluated,
            "filtered_h3_count": h3_eval.filtered_site_count,
            "cell_scores": h3_eval.cell_scores,
            "cell_dimension_scores": h3_eval.cell_dimension_scores,
            "top_h3_results": [r.model_dump() for r in h3_eval.ranked_results],
            "hotspot_results": [r.model_dump() for r in hotspot_eval.ranked_results],
        }

    @application.post("/api/v1/site/{site_id}")
    def inspect_site(site_id: str, req: SiteInspectRequest) -> dict[str, Any]:
        site = store.h3_prepacked.site_by_id.get(site_id) or store.hotspot_prepacked.site_by_id.get(site_id)
        if site is None:
            raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found.")
        res = store.engine.evaluate_single_site(
            site=site,
            target=req.target,
            weights=req.weights,
            mode=req.mode,
        )
        return res.model_dump()

    @application.post("/api/v1/weights/evaluate")
    def evaluate_weights_from_mission(req: WeightEvaluateRequest) -> dict[str, Any]:
        try:
            weights = evaluate_mission_weights(
                mission_description=req.mission_description,
                registry=DEFAULT_REGISTRY,
                prepacked=store.h3_prepacked,
                engine=store.engine,
                llm_client=llm_client,
            )
            return {"weights": weights}
        except LLMConfigurationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except LLMProviderError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.post("/api/v1/export")
    def export_results(
        req: RankRequest,
        format: Literal["csv", "json"] = Query(default="csv"),
    ) -> Response:
        hotspot_eval = store.engine.evaluate_prepacked(
            prepacked=store.hotspot_prepacked,
            target=req.target,
            weights=req.weights,
            mode=req.mode,
            filters=req.filters,
            exclude_well_known=req.exclude_well_known,
            top_k=None,
        )
        h3_eval = store.engine.evaluate_prepacked(
            prepacked=store.h3_prepacked,
            target=req.target,
            weights=req.weights,
            mode=req.mode,
            filters=req.filters,
            exclude_well_known=req.exclude_well_known,
            top_k=req.top_k,
        )
        combined = sorted(
            [*hotspot_eval.ranked_results, *h3_eval.ranked_results],
            key=lambda r: r.overall_score,
            reverse=True,
        )

        if format == "json":
            payload = {
                "target": req.target.model_dump(),
                "mode": req.mode.value,
                "results": [r.model_dump() for r in combined],
            }
            return JSONResponse(
                content=payload,
                headers={"Content-Disposition": 'attachment; filename="isotopos_analogs.json"'},
            )

        buf = io.StringIO()
        writer = csv.writer(buf)
        param_ids = [p.id for p in DEFAULT_REGISTRY.parameters]
        writer.writerow(
            [
                "site_id",
                "site_name",
                "site_type",
                "region",
                "lat",
                "lon",
                "is_well_known",
                "overall_score_pct",
                "strongest_dimensions",
                "diverging_dimensions",
                *param_ids,
            ]
        )
        for r in combined:
            writer.writerow(
                [
                    r.site.id,
                    r.site.name,
                    r.site.site_type,
                    r.site.region,
                    r.site.lat,
                    r.site.lon,
                    r.site.is_well_known,
                    round(r.overall_score * 100.0, 2),
                    "; ".join(r.strongest_dimensions),
                    "; ".join(r.diverging_dimensions),
                    *[r.site.parameters.get(pid, "") for pid in param_ids],
                ]
            )

        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="isotopos_analogs.csv"'},
        )

    return application


app = create_app()
