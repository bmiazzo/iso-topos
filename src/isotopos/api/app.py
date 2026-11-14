"""FastAPI application factory and REST endpoints (FR-1..FR-15, DR-2, DR-3, NFR-1, DEC-005)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from isotopos.api.datastore import DataStore, get_default_datastore
from isotopos.api.exporters import EXPORTERS, export_ranked_analogs
from isotopos.api.schemas import (
    ExportFormat,
    RankRequest,
    SiteInspectRequest,
    TargetExtractRequest,
    WeightEvaluateRequest,
)
from isotopos.core.registry import DEFAULT_REGISTRY
from isotopos.scoring.llm_client import LLMClient, LLMConfigurationError, LLMProviderError
from isotopos.scoring.mission_weights import evaluate_mission_weights

__all__ = [
    "DataStore",
    "EXPORTERS",
    "RankRequest",
    "SiteInspectRequest",
    "TargetExtractRequest",
    "WeightEvaluateRequest",
    "app",
    "create_app",
]


def create_app(
    data_dir: Path | None = None,
    llm_client: LLMClient | None = None,
    store: DataStore | None = None,
) -> FastAPI:
    """Create and configure the iso-topos FastAPI application."""
    application = FastAPI(
        title="iso-topos API",
        description="Planetary-to-Earth Analog Discovery & Characterization Engine",
        version="0.2.0",
    )
    application.add_middleware(GZipMiddleware, minimum_size=1000)

    active_store = (
        store
        if store is not None
        else (DataStore(data_dir=data_dir) if data_dir is not None else get_default_datastore())
    )
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
            "h3_cell_count": len(active_store.h3_sites),
            "hotspot_count": len(active_store.hotspots),
            "preset_count": len(active_store.presets),
        }

    @application.get("/api/v1/metadata")
    def get_metadata() -> dict[str, Any]:
        return {
            "dimensions": [d.model_dump() for d in DEFAULT_REGISTRY.dimensions],
            "parameters": [p.model_dump() for p in DEFAULT_REGISTRY.parameters],
            "presets": [p.model_dump() for p in active_store.presets],
            "hotspots": [h.model_dump() for h in active_store.hotspots],
        }

    @application.get("/api/v1/earth-grid")
    def get_earth_grid() -> JSONResponse:
        return JSONResponse(content=active_store.earth_geojson)

    @application.get("/api/v1/earth-grid/parameter/{param_id}")
    def get_earth_grid_parameter(param_id: str) -> dict[str, Any]:
        if param_id not in active_store.h3_prepacked.param_col_index:
            raise HTTPException(status_code=404, detail=f"Unknown parameter_id '{param_id}'")
        return {
            "parameter_id": param_id,
            "values": active_store.h3_prepacked.get_parameter_map(param_id),
        }

    @application.post("/api/v1/target/extract")
    def extract_target(req: TargetExtractRequest) -> dict[str, Any]:
        if req.preset_id:
            try:
                return active_store.interpolator.extract_preset(req.preset_id).model_dump()
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

        if req.body is not None and req.lat is not None and req.lon is not None:
            return active_store.interpolator.extract_coordinate(
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
        h3_eval = active_store.engine.evaluate_prepacked(
            prepacked=active_store.h3_prepacked,
            target=req.target,
            weights=req.weights,
            mode=req.mode,
            filters=req.filters,
            exclude_well_known=req.exclude_well_known,
            top_k=req.top_k,
            include_dimension_scores=req.dimension_id is not None,
            dimension_id=req.dimension_id,
        )
        hotspot_eval = active_store.engine.evaluate_prepacked(
            prepacked=active_store.hotspot_prepacked,
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
        site = (
            active_store.h3_prepacked.site_by_id.get(site_id)
            or active_store.hotspot_prepacked.site_by_id.get(site_id)
        )
        if site is None:
            raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found.")
        res = active_store.engine.evaluate_single_site(
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
                prepacked=active_store.h3_prepacked,
                engine=active_store.engine,
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
        format: ExportFormat = Query(default="csv"),
    ) -> Response:
        hotspot_eval = active_store.engine.evaluate_prepacked(
            prepacked=active_store.hotspot_prepacked,
            target=req.target,
            weights=req.weights,
            mode=req.mode,
            filters=req.filters,
            exclude_well_known=req.exclude_well_known,
            top_k=None,
        )
        h3_eval = active_store.engine.evaluate_prepacked(
            prepacked=active_store.h3_prepacked,
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
        return export_ranked_analogs(
            fmt=format,
            target=req.target,
            mode=req.mode,
            results=combined,
            registry=DEFAULT_REGISTRY,
        )

    return application


app = create_app()
