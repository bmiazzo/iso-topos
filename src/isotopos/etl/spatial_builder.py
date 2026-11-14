"""Offline spatial index builder: Adaptive Earth H3 grid & Moon/Mars planetocentric grids."""

from __future__ import annotations

import math
from typing import Any

import h3
import numpy as np

from isotopos.core.models import EarthSite, PlanetaryBody
from isotopos.etl.catalog_data import EARTH_HOTSPOTS, PLANETARY_PRESETS


def compute_grazing_sun_hours(lat_deg: float, obliquity_deg: float = 23.44) -> float:
    """Compute annual hours with solar elevation between 0 and 5 deg (parameters.md)."""
    lat_rad = math.radians(max(-89.9, min(89.9, lat_deg)))
    sin_lat = math.sin(lat_rad)
    cos_lat = math.cos(lat_rad)
    obliq_rad = math.radians(obliquity_deg)

    # Sample 73 days x 48 half-hour slots = 3504 points across the year
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


def _is_earth_land(lat: float, lon: float) -> bool:
    """Lightweight deterministic continental & major-island land mask.

    Excludes |lat| > 84.5 deg to stay strictly inside Web Mercator's +-85.05 deg
    tiling domain and avoid polar-cap polygon distortion in MapLibre GL JS.
    """
    if abs(lat) > 84.5:
        return False
    # Antarctica
    if lat <= -64.0:
        return True
    # Greenland & Canadian Arctic Archipelago
    if 60.0 <= lat <= 83.5 and -125.0 <= lon <= -15.0:
        return True
    # North America
    if 15.0 <= lat <= 71.0 and -168.0 <= lon <= -52.0:
        # Exclude Gulf of Mexico / Caribbean open ocean
        if lat < 28.0 and -95.0 <= lon <= -60.0 and not (18.0 <= lat <= 24.0 and -105.0 <= lon <= -87.0):
            return False
        if lat < 52.0 and lon < -130.0:
            return False
        return True
    # South America
    if -56.0 <= lat <= 12.0 and -81.0 <= lon <= -34.5:
        if lat < -20.0 and lon > -50.0:
            return False
        if lat > -5.0 and lon < -80.0:
            return False
        return True
    # Europe & Iceland & Svalbard
    if 36.0 <= lat <= 79.5 and -25.0 <= lon <= 60.0:
        if lat > 71.0 and not (76.0 <= lat <= 80.5 and 10.0 <= lon <= 32.0):
            return False
        return True
    # Africa & Madagascar
    if -35.0 <= lat <= 37.0 and -17.5 <= lon <= 51.5:
        if lat < 4.5 and lon < 8.5:
            return False
        if lat < -10.0 and lon > 41.0 and not (-26.0 <= lat <= -12.0 and 43.0 <= lon <= 50.5):
            return False
        return True
    # Asia (Mainland + Japan + Arabia + India + SE Asia)
    if 8.0 <= lat <= 77.0 and 35.0 <= lon <= 179.0:
        if lat < 20.0 and 55.0 <= lon <= 72.0:
            return False
        if lat < 18.0 and 82.0 <= lon <= 95.0:
            return False
        if lat > 72.0 and lon > 140.0:
            return False
        return True
    # Australia & New Zealand
    if -47.0 <= lat <= -11.0 and 113.0 <= lon <= 179.0:
        if lat < -39.0 and lon < 165.0:
            return False
        if -34.0 <= lat <= -11.0 and lon > 154.0:
            return False
        return True
    # Hawaii (Volcanic hotspot region)
    if 18.5 <= lat <= 22.5 and -160.5 <= lon <= -154.5:
        return True
    return False


def _is_planetary_analog_priority_zone(lat: float, lon: float) -> bool:
    """Identify regions refined from H3 Res 2 to Res 3 (polar, arid, volcanic, alpine, craters)."""
    if abs(lat) >= 64.0:
        return True
    # Sahara, Arabia, Lut, Central Asia, Qaidam/Gobi
    if 15.0 <= lat <= 43.0 and -16.0 <= lon <= 108.0:
        return True
    # Atacama, Puna, Andes Altiplano
    if -32.0 <= lat <= -14.0 and -72.0 <= lon <= -63.0:
        return True
    # SW USA / Basin & Range / Meteor Crater
    if 30.0 <= lat <= 42.0 and -118.0 <= lon <= -104.0:
        return True
    # Australian Outback / Pilbara
    if -30.0 <= lat <= -18.0 and 114.0 <= lon <= 140.0:
        return True
    # Iceland, East Africa Rift, Hawaii, Canaries, Etna
    if (63.0 <= lat <= 67.0 and -25.0 <= lon <= -13.0) or (18.5 <= lat <= 22.5 and -160.5 <= lon <= -154.5):
        return True
    return False


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


def _safe_hex_polygon(cell_id: str) -> list[list[float]] | None:
    """Convert H3 cell boundary to GeoJSON [lon, lat] ring safe for Web Mercator & 3D Globe."""
    boundary = h3.cell_to_boundary(cell_id)  # list of (lat, lon)
    lons = [pt[1] for pt in boundary]
    lats = [max(-84.95, min(84.95, pt[0])) for pt in boundary]

    if max(lons) - min(lons) > 90.0:
        return None

    ring = [[round(ln, 4), round(lt, 4)] for ln, lt in zip(lons, lats)]
    ring.append(ring[0])
    return ring


def build_earth_h3_grid(max_cells: int | None = None) -> tuple[list[EarthSite], dict[str, Any]]:
    """Build Adaptive H3 Earth Land Grid (Res 2 globally + Res 3 in analog priority zones)."""
    res2_cells: list[str] = []
    for r0 in h3.get_res0_cells():
        res2_cells.extend(h3.cell_to_children(r0, 2))

    adaptive_cells: list[str] = []
    for cell_id in res2_cells:
        lat, lon = h3.cell_to_latlng(cell_id)
        if not _is_earth_land(lat, lon):
            continue
        if _is_planetary_analog_priority_zone(lat, lon):
            adaptive_cells.extend(h3.cell_to_children(cell_id, 3))
        else:
            adaptive_cells.append(cell_id)

    if max_cells is not None:
        adaptive_cells = adaptive_cells[:max_cells]

    sites: list[EarthSite] = []
    features: list[dict[str, Any]] = []

    for cell_id in adaptive_cells:
        ring = _safe_hex_polygon(cell_id)
        if ring is None:
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
            name=f"H3 {cell_id[:7]} ({lat:.1f}°, {lon:.1f}°)",
            region=region_tag,
            site_type="h3_cell",
            lat=round(lat, 4),
            lon=round(lon, 4),
            is_well_known=False,
            feature_category="h3_adaptive_cell",
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
                    "lat": site.lat,
                    "lon": site.lon,
                    **params,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [ring],
                },
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
