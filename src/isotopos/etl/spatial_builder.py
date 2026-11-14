"""Offline spatial index builder: Uniform H3 Res 4 Earth Land Grid & Moon/Mars grids."""

from __future__ import annotations

from typing import Any

import h3

from isotopos.core.models import EarthSite, PlanetaryBody
from isotopos.etl.geodesic_math import (
    blend_with_anchors,
    compute_grazing_sun_hours,
    geodesic_deg as _geodesic_deg,
    sigmoid as _sigmoid,
    soft_province_field as _soft_province_field,
    spherical_noise as _spherical_noise,
)
from isotopos.etl.h3_geometry import (
    ANALOG_ISLANDS_LATLON as _ANALOG_ISLANDS_LATLON,
    clip_antimeridian_halfplane as _clip_antimeridian_halfplane,
    close_rounded_ring as _close_rounded_ring,
    load_land_h3_cells as _load_land_h3_cells,
    safe_hex_geometry as _safe_hex_geometry,
    safe_hex_polygon as _safe_hex_polygon,
)
from isotopos.etl.parameter_synthesizer import (
    is_near_well_known_baseline as _is_near_well_known_baseline,
    synthesize_earth_cell_parameters as _synthesize_earth_cell_parameters,
    synthesize_planetary_point as _synthesize_planetary_point,
)

__all__ = [
    "build_earth_h3_grid",
    "build_planetary_grid",
    "compute_grazing_sun_hours",
    "blend_with_anchors",
    "_load_land_h3_cells",
    "_safe_hex_geometry",
    "_safe_hex_polygon",
    "_synthesize_earth_cell_parameters",
    "_synthesize_planetary_point",
    "_is_near_well_known_baseline",
    "_geodesic_deg",
    "_soft_province_field",
    "_sigmoid",
    "_spherical_noise",
    "_clip_antimeridian_halfplane",
    "_close_rounded_ring",
    "_ANALOG_ISLANDS_LATLON",
]


def build_earth_h3_grid(
    max_cells: int | None = None,
    res: int = 4,
) -> tuple[list[EarthSite], dict[str, Any]]:
    """Build Uniform H3 Earth Land Grid (default Res 4) using Natural Earth 50m coastlines."""
    land_cells = sorted(_load_land_h3_cells(res=res))
    if max_cells is not None:
        land_cells = land_cells[:max_cells]

    sites: list[EarthSite] = []
    features: list[dict[str, Any]] = []

    for cell_id in land_cells:
        geom = _safe_hex_geometry(cell_id)
        if geom is None:
            continue

        lat, lon = h3.cell_to_latlng(cell_id)
        params = _synthesize_earth_cell_parameters(lat, lon)
        region_tag = (
            "Polar" if abs(lat) >= 64.0
            else "Arid / Desert" if params["aridity_dryness_index"] >= 0.78
            else "Highland / Plateau" if params["elevation_m"] >= 2000.0
            else "Continental"
        )
        site = EarthSite(
            id=cell_id,
            name=f"H3 {cell_id[:8]} ({lat:.1f}°, {lon:.1f}°)",
            region=region_tag,
            site_type="h3_cell",
            lat=round(lat, 4),
            lon=round(lon, 4),
            is_well_known=_is_near_well_known_baseline(lat, lon),
            feature_category=f"h3_res{res}_cell",
            parameters=params,
        )
        sites.append(site)

        features.append(
            {
                "type": "Feature",
                "id": cell_id,
                "properties": {
                    "id": cell_id,
                    "name": site.name,
                    "region": region_tag,
                },
                "geometry": geom,
            }
        )

    return sites, {"type": "FeatureCollection", "features": features}


def build_planetary_grid(body: PlanetaryBody, step_deg: float = 5.0) -> dict[str, Any]:
    """Build a regular planetocentric (lat, lon) grid for Moon or Mars parameter extraction."""
    lats = [round(-90.0 + i * step_deg, 4) for i in range(int(180.0 / step_deg) + 1)]
    lons = [round(i * step_deg, 4) for i in range(int(360.0 / step_deg))]  # 0 .. 360-step

    cells: list[list[dict[str, float]]] = []
    for lt in lats:
        row: list[dict[str, float]] = []
        for ln in lons:
            row.append(_synthesize_planetary_point(body, lt, ln))
        cells.append(row)

    return {
        "body": body.value,
        "step_deg": step_deg,
        "lats": lats,
        "lons": lons,
        "values": cells,
    }
