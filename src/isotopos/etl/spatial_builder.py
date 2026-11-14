"""Offline spatial index builder: Uniform H3 Res 4 Earth Land Grid & Moon/Mars grids."""

from __future__ import annotations

import functools
import json
import math
from pathlib import Path
from typing import Any

import h3
import numpy as np

from isotopos.core.models import EarthSite, PlanetaryBody
from isotopos.etl.catalog_data import EARTH_HOTSPOTS, PLANETARY_PRESETS

_LAND_CELL_CACHE: dict[int, set[str]] = {}

# Key volcanic, polar, and oceanic analog islands guaranteed in the land mask
_ANALOG_ISLANDS_LATLON: tuple[tuple[float, float], ...] = (
    (19.8207, -155.4681),  # Hawaii (Mauna Kea / Big Island)
    (20.7097, -156.2533),  # Maui (Haleakala)
    (65.0300, -16.7500),   # Iceland (Askja / Holuhraun)
    (63.9800, -22.6000),   # Iceland (Reykjanes)
    (78.9000, 16.0000),    # Svalbard (Spitsbergen)
    (79.8000, 22.0000),    # Svalbard (Nordaustlandet)
    (29.0000, -13.6800),   # Canary Islands (Lanzarote)
    (28.2700, -16.6400),   # Canary Islands (Tenerife / Teide)
    (28.7600, -17.8900),   # Canary Islands (La Palma)
    (38.4700, -28.4000),   # Azores (Pico)
    (-0.8300, -91.1300),   # Galapagos (Sierra Negra)
    (-19.0000, 47.0000),   # Madagascar
    (-62.9700, -60.6500),  # Deception Island (Antarctica)
    (-49.3500, 70.2200),   # Kerguelen Islands
    (75.4300, -89.6500),   # Devon Island (Haughton Crater)
    (79.4000, -90.8000),   # Axel Heiberg Island
)


@functools.lru_cache(maxsize=8192)
def _cached_grazing_sun_hours(quantized_lat: float, quant_obliq: float) -> float:
    lat_rad = math.radians(max(-89.9, min(89.9, quantized_lat)))
    sin_lat = math.sin(lat_rad)
    cos_lat = math.cos(lat_rad)
    obliq_rad = math.radians(quant_obliq)

    days = np.linspace(0.0, 365.0, 73, endpoint=False)
    hours = np.linspace(0.0, 24.0, 48, endpoint=False)
    decl = obliq_rad * np.sin(2.0 * math.pi * (days - 80.0) / 365.0)
    ha = np.radians(15.0 * (hours - 12.0))

    sin_elev = (
        sin_lat * np.sin(decl)[:, None]
        + cos_lat * np.cos(decl)[:, None] * np.cos(ha)[None, :]
    )
    elev_deg = np.degrees(np.arcsin(np.clip(sin_elev, -1.0, 1.0)))
    grazing_frac = float(np.mean((elev_deg >= 0.0) & (elev_deg <= 5.0)))
    return round(grazing_frac * 8760.0, 1)


def compute_grazing_sun_hours(lat_deg: float, obliquity_deg: float = 23.44) -> float:
    """Compute annual hours with solar elevation between 0 and 5 deg (parameters.md)."""
    return _cached_grazing_sun_hours(round(float(lat_deg), 2), round(float(obliquity_deg), 2))


def _load_land_h3_cells(res: int = 4) -> set[str]:
    """Extract H3 land cells from Natural Earth 50m Land polygons + curated islands/hotspots."""
    if res in _LAND_CELL_CACHE:
        return _LAND_CELL_CACHE[res]

    root = Path(__file__).resolve().parents[3]
    ne_path = root / "data" / "raw" / "ne_50m_land.geojson"
    cache_path = root / "data" / "raw" / f"ne_50m_h3_res{res}_cells.json"

    if cache_path.exists():
        cells = set(json.loads(cache_path.read_text(encoding="utf-8")))
        _LAND_CELL_CACHE[res] = cells
        return cells

    cells: set[str] = set()
    if ne_path.exists():
        geo = json.loads(ne_path.read_text(encoding="utf-8"))
        for feat in geo["features"]:
            geom = feat["geometry"]
            polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
            for poly in polys:
                outer = [(max(-84.5, min(84.5, lat)), lon) for lon, lat in poly[0]]
                if len(outer) < 3:
                    continue
                holes = [
                    [(max(-84.5, min(84.5, lat)), lon) for lon, lat in hole]
                    for hole in poly[1:]
                    if len(hole) >= 3
                ]
                h3_poly = h3.LatLngPoly(outer, *holes)
                try:
                    extracted = h3.polygon_to_cells_experimental(h3_poly, res, contain="overlap")
                except Exception:
                    extracted = h3.polygon_to_cells(h3_poly, res)
                cells.update(extracted)

    # Guarantee all curated Earth hotspots and key volcanic/polar analog islands are included
    for hs in EARTH_HOTSPOTS:
        if abs(hs.lat) <= 84.5:
            cells.add(h3.latlng_to_cell(hs.lat, hs.lon, res))
    for lat, lon in _ANALOG_ISLANDS_LATLON:
        if abs(lat) <= 84.5:
            cells.add(h3.latlng_to_cell(lat, lon, res))

    # Strictly filter out polar cap cells beyond Web Mercator's +-84.5 deg safe band
    cells = {cid for cid in cells if abs(h3.cell_to_latlng(cid)[0]) <= 84.5}

    if ne_path.exists():
        cache_path.write_text(
            json.dumps(sorted(cells), separators=(",", ":")),
            encoding="utf-8",
        )

    _LAND_CELL_CACHE[res] = cells
    return cells


def _clip_antimeridian_halfplane(
    pts_360: list[tuple[float, float]],
    keep_le_180: bool,
) -> list[tuple[float, float]]:
    """Sutherland-Hodgman clip of an unwrapped [0, 360] ring against x = 180.0."""
    out: list[tuple[float, float]] = []
    n = len(pts_360)
    for i in range(n):
        x1, y1 = pts_360[i]
        x2, y2 = pts_360[(i + 1) % n]
        in1 = (x1 <= 180.0) if keep_le_180 else (x1 >= 180.0)
        in2 = (x2 <= 180.0) if keep_le_180 else (x2 >= 180.0)
        if in1 and in2:
            out.append((x2, y2))
        elif in1 and not in2:
            t = (180.0 - x1) / (x2 - x1) if x2 != x1 else 0.0
            out.append((180.0, y1 + t * (y2 - y1)))
        elif not in1 and in2:
            t = (180.0 - x1) / (x2 - x1) if x2 != x1 else 0.0
            out.append((180.0, y1 + t * (y2 - y1)))
            out.append((x2, y2))
    return out


def _close_rounded_ring(pts: list[tuple[float, float]]) -> list[list[float]] | None:
    if len(pts) < 3:
        return None
    ring = [[round(ln, 4), round(lt, 4)] for ln, lt in pts]
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring if len(ring) >= 4 else None


def _safe_hex_geometry(cell_id: str) -> dict[str, Any] | None:
    """Convert H3 cell boundary to GeoJSON Polygon or antimeridian-split MultiPolygon."""
    boundary = h3.cell_to_boundary(cell_id)  # list of (lat, lon)
    lons = [pt[1] for pt in boundary]
    lats = [max(-84.95, min(84.95, pt[0])) for pt in boundary]
    lon_span = max(lons) - min(lons)

    if lon_span <= 90.0:
        ring = [[round(ln, 4), round(lt, 4)] for ln, lt in zip(lons, lats)]
        ring.append(ring[0])
        return {"type": "Polygon", "coordinates": [ring]}

    if lon_span > 180.0:
        # Unwrap to [0, 360] and check whether this is a valid antimeridian crossing
        pts_360 = [(ln if ln >= 0.0 else ln + 360.0, lt) for ln, lt in zip(lons, lats)]
        xs_360 = [p[0] for p in pts_360]
        if max(xs_360) - min(xs_360) <= 90.0:
            east_pts = _clip_antimeridian_halfplane(pts_360, keep_le_180=True)
            west_pts = [
                (x - 360.0, y)
                for x, y in _clip_antimeridian_halfplane(pts_360, keep_le_180=False)
            ]
            east_ring = _close_rounded_ring(east_pts)
            west_ring = _close_rounded_ring(west_pts)
            polys = []
            if east_ring is not None:
                polys.append([east_ring])
            if west_ring is not None:
                polys.append([west_ring])
            if len(polys) == 2:
                return {"type": "MultiPolygon", "coordinates": polys}
            if len(polys) == 1:
                return {"type": "Polygon", "coordinates": polys[0]}

    return None


def _safe_hex_polygon(cell_id: str) -> list[list[float]] | None:
    """Legacy single-ring helper returning the first ring of _safe_hex_geometry."""
    geom = _safe_hex_geometry(cell_id)
    if geom is None:
        return None
    if geom["type"] == "Polygon":
        return geom["coordinates"][0]
    return geom["coordinates"][0][0]


def _synthesize_earth_cell_parameters(lat: float, lon: float) -> dict[str, float]:
    """Derive physically grounded 17-parameter vector for an Earth (lat, lon) cell."""
    abs_lat = abs(lat)
    grazing = compute_grazing_sun_hours(lat)

    # Regional climate & terrain baselines
    is_polar = abs_lat >= 65.0
    is_arid_belt = (16.0 <= abs_lat <= 38.0) and (
        (-120.0 <= lon <= -64.0) or (-16.0 <= lon <= 108.0) or (114.0 <= lon <= 142.0)
    )
    is_tibetan_andes = (27.0 <= lat <= 40.0 and 75.0 <= lon <= 102.0) or (
        -28.0 <= lat <= -14.0 and -71.0 <= lon <= -65.0
    )

    # Elevation & Slope
    elevation_m = 350.0 + 450.0 * abs(math.sin(math.radians(lon * 2.1))) * math.cos(math.radians(lat))
    if is_tibetan_andes:
        elevation_m = 3800.0 + 700.0 * math.cos(math.radians(lat * 3.0))
    elif lat <= -72.0:
        elevation_m = 2200.0 + 600.0 * abs(math.sin(math.radians(lon)))

    slope_deg = 3.5 + 8.0 * abs(math.sin(math.radians(lat * 4.0 + lon * 1.7)))
    if is_tibetan_andes or (58.0 <= lat <= 70.0 and -60.0 <= lon <= 20.0):
        slope_deg = min(32.0, slope_deg + 8.5)

    roughness = min(0.95, 0.25 + slope_deg / 40.0)

    # Temperature & Diurnal Swing
    base_temp = 27.0 - 0.72 * abs_lat - 0.0055 * max(0.0, elevation_m)
    if lat <= -68.0:
        base_temp = min(base_temp, -28.0 - 0.35 * (abs_lat - 68.0))
    mean_temp_c = max(-56.0, min(42.0, base_temp))

    diurnal = 10.0 + (15.0 if is_arid_belt else 2.0) + (4.0 if is_tibetan_andes else 0.0)
    diurnal = max(3.0, min(35.0, diurnal))

    # Illumination
    solar_illum = max(0.25, min(0.9, 0.78 - 0.0045 * abs_lat + (0.12 if is_arid_belt else 0.0)))

    # Water, Ice & Permafrost
    aridity = 0.85 if is_arid_belt else (0.72 if is_polar else 0.38)
    aridity = max(0.05, min(0.98, aridity + 0.06 * math.sin(math.radians(lon * 2.5))))
    permafrost = max(0.0, min(0.96, (abs_lat - 54.0) / 26.0)) if abs_lat > 54.0 else (0.15 if elevation_m > 3600 else 0.0)
    cold_trap = max(0.0, min(0.95, permafrost * aridity))

    # Geology & Magnetism
    anorthosite = 0.1
    if (60.0 <= lat <= 72.0 and -66.0 <= lon <= -42.0) or (66.0 <= lat <= 70.0 and 10.0 <= lon <= 20.0):
        anorthosite = 0.78
    elif 50.0 <= lat <= 62.0 and -80.0 <= lon <= -55.0:
        anorthosite = 0.65

    basalt = 0.28 + 0.25 * max(0.0, math.sin(math.radians(lat * 3.0 - lon * 2.0)))
    if (63.0 <= lat <= 67.0 and -25.0 <= lon <= -13.0) or (18.5 <= lat <= 22.5 and -160.5 <= lon <= -154.5):
        basalt = 0.92
    elif 10.0 <= lat <= 24.0 and 72.0 <= lon <= 80.0:
        basalt = 0.84

    clay_carb = 0.72 if is_arid_belt else 0.25
    regolith = min(0.99, max(0.15, 0.45 * aridity + 0.45 * (1.0 if is_polar or is_arid_belt else 0.3)))
    magnetic_nt = 80.0 + 380.0 * abs(math.sin(math.radians(lat * 5.0 + lon * 3.0)))

    # Subsurface & Biosignatures
    cave_score = 0.75 if basalt > 0.82 else (0.5 if permafrost > 0.7 else 0.25)
    biosig = 0.68 if (is_arid_belt and clay_carb > 0.65) else 0.3

    # Smoothly blend with nearby curated hotspots within 2.5 degrees
    for hs in EARTH_HOTSPOTS:
        if abs(lat - hs.lat) >= 2.5 or abs(lon - hs.lon) >= 2.5:
            continue
        dist_deg = math.hypot(lat - hs.lat, lon - hs.lon)
        if dist_deg < 2.5:
            blend = 1.0 - dist_deg / 2.5
            p = hs.parameters
            elevation_m = (1 - blend) * elevation_m + blend * p["elevation_m"]
            slope_deg = (1 - blend) * slope_deg + blend * p["slope_deg"]
            roughness = (1 - blend) * roughness + blend * p["roughness_index"]
            anorthosite = (1 - blend) * anorthosite + blend * p["anorthosite_highland_score"]
            basalt = (1 - blend) * basalt + blend * p["basalt_volcanic_score"]
            clay_carb = (1 - blend) * clay_carb + blend * p["clay_carbonate_sediment_score"]
            regolith = (1 - blend) * regolith + blend * p["regolith_rock_abundance"]
            magnetic_nt = (1 - blend) * magnetic_nt + blend * p["magnetic_anomaly_nt"]
            mean_temp_c = (1 - blend) * mean_temp_c + blend * p["mean_temp_c"]
            diurnal = (1 - blend) * diurnal + blend * p["diurnal_amplitude_c"]
            solar_illum = (1 - blend) * solar_illum + blend * p["solar_illumination_frac"]
            aridity = (1 - blend) * aridity + blend * p["aridity_dryness_index"]
            permafrost = (1 - blend) * permafrost + blend * p["subsurface_ice_permafrost"]
            cold_trap = (1 - blend) * cold_trap + blend * p["cold_trap_sublimation_index"]
            cave_score = (1 - blend) * cave_score + blend * p["subsurface_cave_drilling_score"]
            biosig = (1 - blend) * biosig + blend * p["biosignature_preservation_score"]

    return {
        "elevation_m": round(elevation_m, 1),
        "slope_deg": round(slope_deg, 2),
        "roughness_index": round(roughness, 3),
        "anorthosite_highland_score": round(anorthosite, 3),
        "basalt_volcanic_score": round(basalt, 3),
        "clay_carbonate_sediment_score": round(clay_carb, 3),
        "regolith_rock_abundance": round(regolith, 3),
        "magnetic_anomaly_nt": round(magnetic_nt, 1),
        "mean_temp_c": round(mean_temp_c, 2),
        "diurnal_amplitude_c": round(diurnal, 2),
        "solar_illumination_frac": round(solar_illum, 3),
        "low_sun_grazing_hours": grazing,
        "aridity_dryness_index": round(aridity, 3),
        "subsurface_ice_permafrost": round(permafrost, 3),
        "cold_trap_sublimation_index": round(cold_trap, 3),
        "subsurface_cave_drilling_score": round(cave_score, 3),
        "biosignature_preservation_score": round(biosig, 3),
    }


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
            is_well_known=False,
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


def _synthesize_planetary_point(body: PlanetaryBody, lat: float, lon: float) -> dict[str, float]:
    """Generate physically grounded Moon or Mars surface parameters at (lat, lon)."""
    abs_lat = abs(lat)
    lon_360 = lon % 360.0
    obliquity = 1.54 if body == PlanetaryBody.MOON else 25.19
    grazing = compute_grazing_sun_hours(lat, obliquity_deg=obliquity)

    if body == PlanetaryBody.MOON:
        # Nearside mare basins vs. farside/polar anorthositic highlands
        is_nearside_mare = (-35.0 <= lat <= 45.0) and (lon_360 <= 65.0 or lon_360 >= 305.0)
        anorthosite = 0.25 if is_nearside_mare else 0.92
        basalt = 0.88 if is_nearside_mare else 0.08
        elevation_m = -1400.0 if is_nearside_mare else 1600.0 + 1800.0 * math.sin(math.radians(abs_lat))
        slope_deg = 3.0 + (12.0 if not is_nearside_mare else 1.5)
        mean_temp_c = -18.0 - 1.35 * abs_lat
        diurnal = 250.0 * math.cos(math.radians(abs_lat * 0.85))
        ice = max(0.0, min(0.88, (abs_lat - 75.0) / 15.0)) if abs_lat > 75.0 else 0.02
        cold_trap = max(0.0, min(0.95, ice * 1.05))
        mag_nt = 20.0 + (550.0 if (5.0 <= lat <= 12.0 and 295.0 <= lon_360 <= 310.0) else 35.0 * abs(math.sin(math.radians(lon_360 * 3.0))))
        illum = 0.82 if abs_lat >= 84.0 else 0.50
        params = {
            "elevation_m": round(elevation_m, 1),
            "slope_deg": round(slope_deg, 2),
            "roughness_index": round(0.35 + 0.4 * (1.0 - float(is_nearside_mare)), 3),
            "anorthosite_highland_score": round(anorthosite, 3),
            "basalt_volcanic_score": round(basalt, 3),
            "clay_carbonate_sediment_score": 0.0,
            "regolith_rock_abundance": 0.92,
            "magnetic_anomaly_nt": round(mag_nt, 1),
            "mean_temp_c": round(mean_temp_c, 1),
            "diurnal_amplitude_c": round(max(45.0, diurnal), 1),
            "solar_illumination_frac": illum,
            "low_sun_grazing_hours": grazing,
            "aridity_dryness_index": 1.0,
            "subsurface_ice_permafrost": round(ice, 3),
            "cold_trap_sublimation_index": round(cold_trap, 3),
            "subsurface_cave_drilling_score": 0.45,
            "biosignature_preservation_score": 0.0,
        }
    else:
        # Mars: Northern Lowlands (Arcadia/Vastitas) vs. Southern Cratered Highlands vs. Tharsis
        is_north_lowland = lat >= 25.0
        is_tharsis = (-20.0 <= lat <= 25.0) and (225.0 <= lon_360 <= 265.0)
        elevation_m = 6500.0 if is_tharsis else (-3600.0 if is_north_lowland else 1200.0)
        slope_deg = 2.0 if is_north_lowland else 7.5
        basalt = 0.85 if (is_tharsis or is_north_lowland) else 0.68
        clay_carb = 0.72 if (-25.0 <= lat <= 30.0 and not is_tharsis) else 0.35
        mean_temp_c = -48.0 - 0.55 * abs_lat
        diurnal = 80.0 - 0.35 * abs_lat
        ice = max(0.05, min(0.95, (abs_lat - 32.0) / 35.0)) if abs_lat > 32.0 else 0.08
        cold_trap = max(0.05, min(0.92, ice * 0.95))
        mag_nt = 280.0 if lat < -10.0 else 55.0
        params = {
            "elevation_m": round(elevation_m, 1),
            "slope_deg": round(slope_deg, 2),
            "roughness_index": 0.32 if is_north_lowland else 0.55,
            "anorthosite_highland_score": 0.14,
            "basalt_volcanic_score": round(basalt, 3),
            "clay_carbonate_sediment_score": round(clay_carb, 3),
            "regolith_rock_abundance": 0.92,
            "magnetic_anomaly_nt": round(mag_nt, 1),
            "mean_temp_c": round(mean_temp_c, 1),
            "diurnal_amplitude_c": round(diurnal, 1),
            "solar_illumination_frac": 0.49,
            "low_sun_grazing_hours": grazing,
            "aridity_dryness_index": 0.99,
            "subsurface_ice_permafrost": round(ice, 3),
            "cold_trap_sublimation_index": round(cold_trap, 3),
            "subsurface_cave_drilling_score": 0.85 if is_tharsis else 0.55,
            "biosignature_preservation_score": round(0.75 * clay_carb, 3),
        }

    # Blend smoothly with nearby planetary presets
    for preset in PLANETARY_PRESETS:
        if preset.body != body:
            continue
        p_lon = preset.lon % 360.0
        dlon = min(abs(lon_360 - p_lon), 360.0 - abs(lon_360 - p_lon))
        dist = math.hypot(lat - preset.lat, dlon)
        if dist < 12.0:
            w = 1.0 - dist / 12.0
            for k, v in preset.parameters.items():
                params[k] = round((1.0 - w) * params[k] + w * v, 3)

    return params


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
