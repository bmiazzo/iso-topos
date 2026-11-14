"""Pluggable export format serializers for ranked Earth analogs (FR-15, ER-4)."""

from __future__ import annotations

import csv
import io
from collections.abc import Callable

from fastapi.responses import JSONResponse, Response

from isotopos.api.schemas import ExportFormat
from isotopos.core.models import RankedAnalogResult, ScoringMode, TargetLocation
from isotopos.core.registry import DEFAULT_REGISTRY, ParameterRegistry

ExporterFn = Callable[
    [TargetLocation, ScoringMode, list[RankedAnalogResult], ParameterRegistry],
    Response,
]


def _export_json(
    target: TargetLocation,
    mode: ScoringMode,
    results: list[RankedAnalogResult],
    _registry: ParameterRegistry,
) -> Response:
    payload = {
        "target": target.model_dump(),
        "mode": mode.value,
        "results": [r.model_dump() for r in results],
    }
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": 'attachment; filename="isotopos_analogs.json"'},
    )


def _export_csv(
    _target: TargetLocation,
    _mode: ScoringMode,
    results: list[RankedAnalogResult],
    registry: ParameterRegistry,
) -> Response:
    buf = io.StringIO()
    writer = csv.writer(buf)
    param_ids = [p.id for p in registry.parameters]
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
    for r in results:
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


EXPORTERS: dict[ExportFormat, ExporterFn] = {
    "json": _export_json,
    "csv": _export_csv,
}


def export_ranked_analogs(
    fmt: ExportFormat,
    target: TargetLocation,
    mode: ScoringMode,
    results: list[RankedAnalogResult],
    registry: ParameterRegistry = DEFAULT_REGISTRY,
) -> Response:
    """Serialize ranked Earth analog results using the registered exporter for `fmt`."""
    exporter = EXPORTERS.get(fmt)
    if exporter is None:
        raise ValueError(f"Unsupported export format: {fmt!r}")
    return exporter(target, mode, results, registry)
