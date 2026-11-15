"""Offline spatial index builder: Uniform H3 Res 4 Earth Land Grid & Moon/Mars grids."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import h3
import numpy as np

from isotopos.core.models import EarthSite, PlanetaryBody
from isotopos.etl.catalog_data import EARTH_HOTSPOTS
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
from isotopos.etl.sources.baseline_regions import (
    CountryResolver,
    format_h3_display_name,
    is_well_known_baseline_region,
)
from isotopos.etl.sources.earth_datasets import EarthOpenDatasets
from isotopos.etl.sources.hotspot_enrichment import enrich_hotspots_from_datasets
from isotopos.etl.sources.planetary_datasets import MarsOpenDatasets, MoonOpenDatasets

__all__ = [
    "build_earth_h3_grid",
    "build_enriched_hotspots",
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

_DEFAULT_RAW_DIR = Path(__file__).resolve().parents[3] / "data" / "raw"


def _earth_raw_ready(raw_dir: Path) -> bool:
    earth_dir = raw_dir / "earth"
    return all(
        (earth_dir / fname).exists()
        for fname in (
            "emag2_v3_upcont.tif",
            "etopo2v2c_i2_lsb.zip",
            "wc2.1_10m_bio.zip",
            "wc2.1_10m_srad.zip",
            "glim_05deg.zip",
            "modis_landcover.zip",
            "global_aridity_2017.tif",
            "obu_permafrost_25km.nc",
        )
    )


def _moon_raw_ready(raw_dir: Path) -> bool:
    mdir = raw_dir / "moon"
    return (mdir / "ldem_4.img").exists() and (mdir / "T2015_449.sh.gz").exists()


def _mars_raw_ready(raw_dir: Path) -> bool:
    mdir = raw_dir / "mars"
    return (mdir / "megt90n000cb.img").exists() and (mdir / "Langlais2019.sh.gz").exists()


def build_earth_h3_grid(
    max_cells: int | None = None,
    res: int = 4,
    raw_dir: Path | None = None,
    require_real: bool = False,
    earth_ds: EarthOpenDatasets | None = None,
) -> tuple[list[EarthSite], dict[str, Any]]:
    """Build Uniform H3 Earth Land Grid using Natural Earth coastlines and real open Earth rasters."""
    resolved_raw = raw_dir or _DEFAULT_RAW_DIR
    land_cells = sorted(_load_land_h3_cells(res=res))
    if max_cells is not None:
        land_cells = land_cells[:max_cells]

    cell_records: list[tuple[str, float, float, dict[str, Any]]] = []
    for cell_id in land_cells:
        geom = _safe_hex_geometry(cell_id)
        if geom is None:
            continue
        lat, lon = h3.cell_to_latlng(cell_id)
        cell_records.append((cell_id, lat, lon, geom))

    use_real = earth_ds is not None or require_real or (max_cells is None and _earth_raw_ready(resolved_raw))
    if use_real and earth_ds is None:
        if not _earth_raw_ready(resolved_raw):
            raise FileNotFoundError(
                f"Real Earth datasets missing under {resolved_raw / 'earth'}. "
                "Run `python scripts/fetch_open_datasets.py --scope earth` first."
            )
        earth_ds = EarthOpenDatasets.from_raw_dir(resolved_raw)

    sites: list[EarthSite] = []
    features: list[dict[str, Any]] = []

    if earth_ds is not None:
        lats = np.array([r[1] for r in cell_records], dtype=np.float64)
        lons = np.array([r[2] for r in cell_records], dtype=np.float64)
        params_list, interp_list, countries, regions = earth_ds.extract_batch(lats, lons)
    else:
        countries_path = resolved_raw / "ne_50m_admin_0_countries.geojson"
        resolver = CountryResolver(countries_path if countries_path.exists() else None)
        params_list = [_synthesize_earth_cell_parameters(r[1], r[2]) for r in cell_records]
        interp_list = [[] for _ in cell_records]
        countries, regions = [], []
        for _, lat, lon, _ in cell_records:
            c, reg = resolver.resolve(lat, lon)
            countries.append(c)
            regions.append(reg)

    for idx, (cell_id, lat, lon, geom) in enumerate(cell_records):
        params = params_list[idx]
        country = countries[idx]
        region_tag = regions[idx] or (
            "Polar"
            if abs(lat) >= 64.0
            else "Arid / Desert"
            if params["aridity_dryness_index"] >= 0.78
            else "Highland / Plateau"
            if params["elevation_m"] >= 2000.0
            else "Continental"
        )
        in_region, _ = is_well_known_baseline_region(lat, lon)
        well_known = bool(in_region or _is_near_well_known_baseline(lat, lon))
        label = format_h3_display_name(country, region_tag, lat, lon, cell_id)

        site = EarthSite(
            id=cell_id,
            name=label,
            region=region_tag,
            site_type="h3_cell",
            lat=round(lat, 4),
            lon=round(lon, 4),
            is_well_known=well_known,
            feature_category=f"h3_res{res}_cell",
            country=country,
            interpolated_parameters=interp_list[idx],
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
                    "country": country,
                    "is_well_known": well_known,
                    "interpolated_count": len(site.interpolated_parameters),
                },
                "geometry": geom,
            }
        )

    return sites, {"type": "FeatureCollection", "features": features}


def build_enriched_hotspots(
    raw_dir: Path | None = None,
    require_real: bool = False,
    earth_ds: EarthOpenDatasets | None = None,
) -> list[EarthSite]:
    """Return cataloged EARTH_HOTSPOTS enriched with real macro physics, countries, and photo URLs."""
    resolved_raw = raw_dir or _DEFAULT_RAW_DIR
    if earth_ds is None and (require_real or _earth_raw_ready(resolved_raw)):
        if not _earth_raw_ready(resolved_raw):
            raise FileNotFoundError(
                f"Real Earth datasets missing under {resolved_raw / 'earth'}. "
                "Run `python scripts/fetch_open_datasets.py --scope earth` first."
            )
        earth_ds = EarthOpenDatasets.from_raw_dir(resolved_raw)
    return enrich_hotspots_from_datasets(list(EARTH_HOTSPOTS), earth_ds=earth_ds)


def build_planetary_grid(
    body: PlanetaryBody,
    step_deg: float = 5.0,
    raw_dir: Path | None = None,
    require_real: bool = False,
) -> dict[str, Any]:
    """Build a regular planetocentric (lat, lon) grid for Moon or Mars from NASA PDS / SH models."""
    resolved_raw = raw_dir or _DEFAULT_RAW_DIR
    lats = [round(-90.0 + i * step_deg, 4) for i in range(int(180.0 / step_deg) + 1)]
    lons = [round(i * step_deg, 4) for i in range(int(360.0 / step_deg))]  # 0 .. 360-step

    ds = None
    if body == PlanetaryBody.MOON and (require_real or (step_deg <= 2.5 and _moon_raw_ready(resolved_raw))):
        ds = MoonOpenDatasets.from_raw_dir(resolved_raw)
    elif body == PlanetaryBody.MARS and (require_real or (step_deg <= 2.5 and _mars_raw_ready(resolved_raw))):
        ds = MarsOpenDatasets.from_raw_dir(resolved_raw)

    cells: list[list[dict[str, float]]] = []
    if ds is not None:
        lon_arr = np.array(lons, dtype=np.float64)
        for lt in lats:
            lat_arr = np.full(len(lons), lt, dtype=np.float64)
            cells.append(ds.extract_batch(lat_arr, lon_arr))
    else:
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
