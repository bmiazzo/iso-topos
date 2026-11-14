"""Earth and planetary 17-parameter spatial synthesis models (DEC-006)."""

from __future__ import annotations

import math

from isotopos.core.models import PlanetaryBody
from isotopos.etl.catalog_data import EARTH_HOTSPOTS, PLANETARY_PRESETS
from isotopos.etl.geodesic_math import (
    blend_with_anchors,
    compute_grazing_sun_hours,
    geodesic_deg,
    sigmoid,
    soft_province_field,
    spherical_noise,
)

# Physiographic Gaussian lobes: (lat, lon, sigma_lat_deg, sigma_lon_deg, amplitude)
ARID_PROVINCES: tuple[tuple[float, float, float, float, float], ...] = (
    (23.5, 11.0, 7.5, 22.0, 0.94),    # Sahara
    (21.5, 46.0, 6.5, 11.0, 0.92),    # Arabian / Rub' al Khali
    (31.5, 57.0, 5.5, 9.0, 0.86),     # Iranian Plateau / Lut
    (40.5, 86.0, 5.0, 14.0, 0.88),    # Taklamakan / Gobi
    (41.0, 63.0, 5.5, 9.5, 0.80),     # Kyzylkum / Karakum
    (33.5, -112.5, 6.0, 8.5, 0.86),   # Sonoran / Mojave / Great Basin
    (-22.5, -68.5, 7.0, 4.5, 0.92),   # Atacama / Altiplano
    (-41.0, -68.0, 6.5, 4.0, 0.72),   # Patagonian Steppe
    (-23.0, 18.5, 6.0, 7.0, 0.86),    # Namib / Kalahari
    (-25.5, 131.0, 7.5, 14.0, 0.88),  # Australian Outback
    (-79.0, 75.0, 11.0, 45.0, 0.88),  # East Antarctic Polar Desert
)

HIGHLAND_PROVINCES: tuple[tuple[float, float, float, float, float], ...] = (
    (33.5, 87.5, 5.5, 12.0, 0.96),    # Tibetan Plateau / Himalayas
    (-19.5, -67.5, 9.0, 3.2, 0.78),   # Central Andes / Altiplano
    (40.5, -108.5, 7.5, 5.5, 0.48),   # Rockies / Colorado Plateau
    (9.5, 39.5, 5.5, 4.5, 0.45),      # Ethiopian Highlands
    (46.5, 10.5, 2.5, 5.5, 0.40),     # European Alps
    (38.5, 72.0, 3.5, 5.5, 0.72),     # Pamir / Tien Shan
    (-80.5, 65.0, 11.5, 48.0, 0.68),  # East Antarctic Dome
    (72.5, -41.5, 6.5, 6.0, 0.56),    # Greenland Ice Dome
)

ANORTHOSITE_PROVINCES: tuple[tuple[float, float, float, float, float], ...] = (
    (66.5, -52.0, 3.2, 4.2, 0.82),    # West Greenland (Qaqortorsuaq)
    (55.5, -63.5, 4.2, 6.0, 0.68),    # Labrador / Grenville / Mistastin
    (68.2, 14.5, 2.2, 3.0, 0.78),     # Lofoten Complex
    (44.1, -74.0, 2.2, 2.8, 0.62),    # Adirondacks Marcy Massif
    (-25.0, 29.0, 2.8, 3.5, 0.60),    # Bushveld Upper Zone
)

BASALT_PROVINCES: tuple[tuple[float, float, float, float, float], ...] = (
    (65.0, -17.5, 2.4, 3.2, 0.92),    # Iceland
    (19.8, -155.5, 2.2, 2.2, 0.94),   # Hawaii
    (19.5, 75.8, 4.5, 4.2, 0.86),     # Deccan Traps
    (45.5, -118.5, 3.5, 4.5, 0.80),   # Columbia River Basalts
    (66.5, 96.0, 5.5, 10.0, 0.76),    # Siberian Traps
    (11.5, 40.5, 5.5, 4.0, 0.80),     # East African Rift / Afar
    (25.6, 40.0, 3.5, 3.0, 0.84),     # Harrat Khaybar / Arabian volcanic fields
    (37.8, 15.0, 1.8, 2.0, 0.84),     # Etna / Sicily
    (28.6, -15.5, 2.0, 2.5, 0.88),    # Canary Islands
)

_WELL_KNOWN_HOTSPOTS = tuple(hs for hs in EARTH_HOTSPOTS if hs.is_well_known)
_EARTH_HOTSPOT_ANCHORS: tuple[tuple[float, float, dict[str, float]], ...] = tuple(
    (hs.lat, hs.lon, hs.parameters) for hs in EARTH_HOTSPOTS
)
_PLANETARY_PRESET_ANCHORS: dict[PlanetaryBody, tuple[tuple[float, float, dict[str, float]], ...]] = {
    body: tuple(
        (p.lat, p.lon % 360.0, p.parameters)
        for p in PLANETARY_PRESETS
        if p.body == body
    )
    for body in PlanetaryBody
}

_EARTH_ROUND_DIGITS: dict[str, int] = {
    "elevation_m": 1,
    "slope_deg": 2,
    "roughness_index": 3,
    "anorthosite_highland_score": 3,
    "basalt_volcanic_score": 3,
    "clay_carbonate_sediment_score": 3,
    "regolith_rock_abundance": 3,
    "magnetic_anomaly_nt": 1,
    "mean_temp_c": 2,
    "diurnal_amplitude_c": 2,
    "solar_illumination_frac": 3,
    "low_sun_grazing_hours": 1,
    "aridity_dryness_index": 3,
    "subsurface_ice_permafrost": 3,
    "cold_trap_sublimation_index": 3,
    "subsurface_cave_drilling_score": 3,
    "biosignature_preservation_score": 3,
}


def is_near_well_known_baseline(lat: float, lon: float, radius_deg: float = 1.0) -> bool:
    """Return True if (lat, lon) lies within radius_deg of any well-known baseline hotspot."""
    for hs in _WELL_KNOWN_HOTSPOTS:
        if abs(lat - hs.lat) > radius_deg:
            continue
        _, _, dist = geodesic_deg(lat, lon, hs.lat, hs.lon)
        if dist <= radius_deg:
            return True
    return False


def synthesize_earth_cell_parameters(lat: float, lon: float) -> dict[str, float]:
    """Derive smooth, continuous, physically grounded 17-parameter vector for Earth (lat, lon)."""
    abs_lat = abs(lat)
    grazing = compute_grazing_sun_hours(lat)
    n1, n2, n3 = spherical_noise(lat, lon)

    arid_field = soft_province_field(lat, lon, ARID_PROVINCES)
    highland_field = soft_province_field(lat, lon, HIGHLAND_PROVINCES)
    anorth_field = soft_province_field(lat, lon, ANORTHOSITE_PROVINCES)
    basalt_field = soft_province_field(lat, lon, BASALT_PROVINCES)

    polar_factor = sigmoid((abs_lat - 64.0) / 5.5)
    antarctic_factor = sigmoid((-66.0 - lat) / 4.5)

    base_elev = 240.0 + 320.0 * abs(n1) + 180.0 * max(0.0, n2)
    elevation_m = base_elev + 4250.0 * highland_field + 950.0 * antarctic_factor * (1.0 - highland_field)
    elevation_m = max(-150.0, min(5400.0, elevation_m))

    slope_deg = (
        2.6
        + 6.2 * abs(n2)
        + 13.5 * highland_field
        + 4.5 * basalt_field
        + 3.5 * polar_factor * (1.0 - antarctic_factor)
    )
    slope_deg = max(0.3, min(34.0, slope_deg))
    roughness = min(0.95, 0.18 + slope_deg / 38.0 + 0.12 * basalt_field)

    lapse_temp = 27.5 - 0.72 * abs_lat - 0.0062 * max(0.0, elevation_m) + 2.5 * n1
    mean_temp_c = lapse_temp - 16.0 * antarctic_factor
    mean_temp_c = max(-56.0, min(42.0, mean_temp_c))

    diurnal = 8.5 + 17.5 * arid_field + 5.5 * highland_field + 2.5 * abs(n3) - 3.5 * polar_factor
    diurnal = max(3.0, min(35.0, diurnal))

    solar_illum = 0.74 - 0.0042 * abs_lat + 0.16 * arid_field + 0.04 * n2
    solar_illum = max(0.24, min(0.92, solar_illum))

    subtrop_belt = math.exp(-0.5 * ((abs_lat - 25.0) / 11.0) ** 2)
    aridity = 0.24 + 0.66 * arid_field + 0.12 * subtrop_belt + 0.26 * polar_factor + 0.06 * n3
    aridity = max(0.06, min(0.98, aridity))

    temp_permafrost = sigmoid((-2.5 - mean_temp_c) / 4.8)
    lat_permafrost = sigmoid((abs_lat - 58.0) / 5.0)
    permafrost = max(temp_permafrost, 0.85 * lat_permafrost)
    permafrost = max(0.0, min(0.96, permafrost))
    cold_trap = max(0.0, min(0.95, permafrost * (0.35 + 0.65 * aridity)))

    anorthosite = max(0.04, min(0.96, 0.06 + 0.84 * anorth_field + 0.04 * max(0.0, n1)))
    basalt = max(0.05, min(0.96, 0.18 + 0.74 * basalt_field + 0.14 * max(0.0, n2)))
    clay_carb = max(0.05, min(0.95, 0.16 + 0.62 * arid_field * (1.0 - 0.55 * polar_factor) + 0.08 * abs(n1)))
    regolith = max(0.15, min(0.99, 0.22 + 0.58 * aridity + 0.22 * polar_factor + 0.08 * highland_field))
    magnetic_nt = 65.0 + 360.0 * abs(n3) + 180.0 * basalt_field + 120.0 * anorth_field

    cave_score = max(0.15, min(0.96, 0.20 + 0.62 * basalt_field + 0.30 * permafrost + 0.06 * abs(n2)))
    biosig = max(0.10, min(0.94, 0.18 + 0.58 * clay_carb * (0.4 + 0.6 * arid_field) * (1.0 - 0.65 * polar_factor)))

    base_params: dict[str, float] = {
        "elevation_m": elevation_m,
        "slope_deg": slope_deg,
        "roughness_index": roughness,
        "anorthosite_highland_score": anorthosite,
        "basalt_volcanic_score": basalt,
        "clay_carbonate_sediment_score": clay_carb,
        "regolith_rock_abundance": regolith,
        "magnetic_anomaly_nt": magnetic_nt,
        "mean_temp_c": mean_temp_c,
        "diurnal_amplitude_c": diurnal,
        "solar_illumination_frac": solar_illum,
        "low_sun_grazing_hours": grazing,
        "aridity_dryness_index": aridity,
        "subsurface_ice_permafrost": permafrost,
        "cold_trap_sublimation_index": cold_trap,
        "subsurface_cave_drilling_score": cave_score,
        "biosignature_preservation_score": biosig,
    }

    blended = blend_with_anchors(
        lat=lat,
        lon=lon,
        base_params=base_params,
        anchors=_EARTH_HOTSPOT_ANCHORS,
        max_dist_deg=4.5,
        sigma_deg=1.35,
        max_blend=0.90,
        eps_deg=0.30,
    )
    return {k: round(v, _EARTH_ROUND_DIGITS[k]) for k, v in blended.items()}


def synthesize_planetary_point(body: PlanetaryBody, lat: float, lon: float) -> dict[str, float]:
    """Generate smooth, physically grounded Moon or Mars surface parameters at (lat, lon)."""
    abs_lat = abs(lat)
    lon_360 = lon % 360.0
    obliquity = 1.54 if body == PlanetaryBody.MOON else 25.19
    grazing = compute_grazing_sun_hours(lat, obliquity_deg=obliquity)

    if body == PlanetaryBody.MOON:
        mare_lobes = (
            (18.0, 338.0, 22.0, 26.0, 0.94),   # Oceanus Procellarum / Imbrium
            (10.0, 30.0, 18.0, 24.0, 0.90),    # Mare Serenitatis / Tranquillitatis
            (-16.0, 342.0, 14.0, 18.0, 0.75),  # Mare Nubium / Humorum
        )
        mare_w = soft_province_field(lat, lon_360, mare_lobes)
        anorthosite = 0.92 * (1.0 - mare_w) + 0.25 * mare_w
        basalt = 0.08 * (1.0 - mare_w) + 0.88 * mare_w
        highland_elev = 1600.0 + 1800.0 * math.sin(math.radians(abs_lat))
        elevation_m = highland_elev * (1.0 - mare_w) + (-1400.0) * mare_w
        slope_deg = 3.0 + 12.0 * (1.0 - mare_w) + 1.5 * mare_w
        mean_temp_c = -18.0 - 1.35 * abs_lat
        diurnal = 250.0 * math.cos(math.radians(abs_lat * 0.85))
        ice = 0.02 + 0.86 * sigmoid((abs_lat - 79.0) / 3.2)
        cold_trap = min(0.95, ice * 1.05)
        dlat_rg, dlon_rg, _ = geodesic_deg(lat, lon_360, 7.5, 301.0)
        reiner_gamma = 550.0 * math.exp(-0.5 * ((dlat_rg / 4.0) ** 2 + (dlon_rg / 5.0) ** 2))
        mag_nt = 20.0 + reiner_gamma + 35.0 * abs(math.sin(math.radians(lon_360 * 3.0)))
        illum = 0.50 + 0.32 * sigmoid((abs_lat - 82.0) / 2.2)
        base_params = {
            "elevation_m": elevation_m,
            "slope_deg": slope_deg,
            "roughness_index": 0.35 + 0.4 * (1.0 - mare_w),
            "anorthosite_highland_score": anorthosite,
            "basalt_volcanic_score": basalt,
            "clay_carbonate_sediment_score": 0.0,
            "regolith_rock_abundance": 0.92,
            "magnetic_anomaly_nt": mag_nt,
            "mean_temp_c": mean_temp_c,
            "diurnal_amplitude_c": max(45.0, diurnal),
            "solar_illumination_frac": illum,
            "low_sun_grazing_hours": grazing,
            "aridity_dryness_index": 1.0,
            "subsurface_ice_permafrost": ice,
            "cold_trap_sublimation_index": cold_trap,
            "subsurface_cave_drilling_score": 0.45,
            "biosignature_preservation_score": 0.0,
        }
    else:
        north_lowland_w = sigmoid((lat - 22.0) / 7.5)
        tharsis_w = soft_province_field(lat, lon_360, ((3.0, 246.0, 16.0, 18.0, 0.96),))
        elevation_m = (
            (1200.0 * (1.0 - north_lowland_w) + (-3600.0) * north_lowland_w) * (1.0 - tharsis_w)
            + 6500.0 * tharsis_w
        )
        slope_deg = (7.5 * (1.0 - north_lowland_w) + 2.0 * north_lowland_w) * (1.0 - tharsis_w) + 6.5 * tharsis_w
        basalt = 0.68 + 0.17 * max(north_lowland_w, tharsis_w)
        equatorial_clay_w = math.exp(-0.5 * ((lat - 3.0) / 22.0) ** 2) * (1.0 - tharsis_w)
        clay_carb = 0.32 + 0.42 * equatorial_clay_w
        mean_temp_c = -48.0 - 0.55 * abs_lat - 0.0015 * max(0.0, elevation_m)
        diurnal = 80.0 - 0.35 * abs_lat
        ice = 0.06 + 0.89 * sigmoid((abs_lat - 44.0) / 7.0)
        cold_trap = min(0.92, ice * 0.95)
        mag_nt = 55.0 + 225.0 * sigmoid((-10.0 - lat) / 9.0)
        base_params = {
            "elevation_m": elevation_m,
            "slope_deg": slope_deg,
            "roughness_index": 0.55 * (1.0 - north_lowland_w) + 0.32 * north_lowland_w,
            "anorthosite_highland_score": 0.14,
            "basalt_volcanic_score": basalt,
            "clay_carbonate_sediment_score": clay_carb,
            "regolith_rock_abundance": 0.92,
            "magnetic_anomaly_nt": mag_nt,
            "mean_temp_c": mean_temp_c,
            "diurnal_amplitude_c": diurnal,
            "solar_illumination_frac": 0.49,
            "low_sun_grazing_hours": grazing,
            "aridity_dryness_index": 0.99,
            "subsurface_ice_permafrost": ice,
            "cold_trap_sublimation_index": cold_trap,
            "subsurface_cave_drilling_score": 0.55 + 0.30 * tharsis_w,
            "biosignature_preservation_score": 0.75 * clay_carb,
        }

    blended = blend_with_anchors(
        lat=lat,
        lon=lon_360,
        base_params=base_params,
        anchors=_PLANETARY_PRESET_ANCHORS[body],
        max_dist_deg=16.0,
        sigma_deg=4.5,
        max_blend=0.92,
        eps_deg=0.35,
    )
    return {k: round(v, 3) for k, v in blended.items()}
