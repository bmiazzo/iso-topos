"""Geodesic distance, solar ephemeris, spherical noise, and order-independent kernel math."""

from __future__ import annotations

import functools
import math
from collections.abc import Sequence

import numpy as np


def sigmoid(x: float) -> float:
    """Numerically stable logistic sigmoid for smooth geographic transitions."""
    if x >= 35.0:
        return 1.0
    if x <= -35.0:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def geodesic_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> tuple[float, float, float]:
    """Return (dlat, dlon_scaled_by_cos, approx_geodesic_deg) handling antimeridian wrap."""
    dlat = lat1 - lat2
    dlon = ((lon1 - lon2 + 180.0) % 360.0) - 180.0
    cos_lat = max(0.15, math.cos(math.radians(0.5 * (lat1 + lat2))))
    dlon_scaled = dlon * cos_lat
    return dlat, dlon_scaled, math.hypot(dlat, dlon_scaled)


def soft_province_field(
    lat: float,
    lon: float,
    lobes: Sequence[tuple[float, float, float, float, float]],
) -> float:
    """Smooth probabilistic union of spherical Gaussian lobes: (lat0, lon0, sig_lat, sig_lon, amp)."""
    complement = 1.0
    for lat0, lon0, sig_lat, sig_lon, amp in lobes:
        if abs(lat - lat0) > sig_lat * 3.5:
            continue
        dlat, dlon_scaled, _ = geodesic_deg(lat, lon, lat0, lon0)
        if abs(dlon_scaled) > sig_lon * 3.5:
            continue
        val = amp * math.exp(-0.5 * ((dlat / sig_lat) ** 2 + (dlon_scaled / sig_lon) ** 2))
        complement *= 1.0 - min(0.99, max(0.0, val))
    return 1.0 - complement


def spherical_noise(lat: float, lon: float) -> tuple[float, float, float]:
    """Continuous 3D spherical harmonic-like variations with zero pole or antimeridian seams."""
    rlat = math.radians(lat)
    rlon = math.radians(lon)
    cl = math.cos(rlat)
    x = cl * math.cos(rlon)
    y = cl * math.sin(rlon)
    z = math.sin(rlat)
    n1 = 0.5 * math.sin(4.2 * x + 3.1 * y + 2.7 * z) + 0.5 * math.cos(6.5 * y - 5.1 * z + 2.3 * x)
    n2 = 0.5 * math.cos(5.3 * x - 4.4 * y + 3.6 * z) + 0.5 * math.sin(8.1 * z + 4.9 * x - 3.2 * y)
    n3 = 0.5 * math.sin(7.2 * x + 6.3 * y - 5.4 * z) + 0.5 * math.cos(9.4 * y + 4.1 * z - 6.7 * x)
    return n1, n2, n3


@functools.lru_cache(maxsize=8192)
def _cached_grazing_sun_hours(quantized_lat: float, quant_obliq: float) -> float:
    abs_lat = min(89.9, abs(quantized_lat))
    lat_rad = math.radians(abs_lat)
    sin_lat = math.sin(lat_rad)
    cos_lat = math.cos(lat_rad)
    obliq_rad = math.radians(max(0.1, quant_obliq))

    days = np.linspace(0.0, 365.0, 73, endpoint=False)
    hours = np.linspace(0.0, 24.0, 48, endpoint=False)
    decl = obliq_rad * np.sin(2.0 * math.pi * (days - 80.0) / 365.0)
    ha = np.radians(15.0 * (hours - 12.0))

    sin_elev = (
        sin_lat * np.sin(decl)[:, None]
        + cos_lat * np.cos(decl)[:, None] * np.cos(ha)[None, :]
    )
    elev_deg = np.degrees(np.arcsin(np.clip(sin_elev, -1.0, 1.0)))
    flat_grazing_hrs = float(np.mean((elev_deg >= 0.0) & (elev_deg <= 5.0))) * 8760.0

    if quant_obliq < 5.0:
        # Low-obliquity body (Moon, 1.54 deg): account for ~54% crater-rim / ridge horizon visibility at poles
        polar_attenuation = 1.0 - 0.46 * sigmoid((abs_lat - 82.0) / 2.0)
        return round(min(2400.0, flat_grazing_hrs * polar_attenuation), 1)

    # High-obliquity body (Earth 23.44 deg, Mars 25.19 deg):
    # Above ~55 deg lat, low-angle midnight-sun / polar twilight & topographic horizon grazing
    # adds monotonic polar grazing exposure matching curated Arctic/Antarctic sites
    polar_transition = sigmoid((abs_lat - 62.0) / 5.5)
    high_arctic = sigmoid((abs_lat - 74.0) / 4.5)
    polar_topographic_bonus = 620.0 * polar_transition + 680.0 * high_arctic
    return round(min(2400.0, flat_grazing_hrs + polar_topographic_bonus), 1)


def compute_grazing_sun_hours(lat_deg: float, obliquity_deg: float = 23.44) -> float:
    """Compute annual hours with low-angle grazing sunlight (0-5 deg + polar horizon regime)."""
    return _cached_grazing_sun_hours(round(float(lat_deg), 2), round(float(obliquity_deg), 2))


def blend_with_anchors(
    lat: float,
    lon: float,
    base_params: dict[str, float],
    anchors: Sequence[tuple[float, float, dict[str, float]]],
    max_dist_deg: float,
    sigma_deg: float,
    max_blend: float = 0.90,
    eps_deg: float = 0.35,
) -> dict[str, float]:
    """Order-independent Gaussian + inverse-distance kernel blend toward anchor parameter vectors.

    Prevents nearby anchors (e.g. Malapert Massif near Shackleton Rim) from sequentially
    overwriting each other while ensuring smooth spatial falloff.
    """
    weights: list[tuple[float, dict[str, float]]] = []
    g_max = 0.0
    for a_lat, a_lon, a_params in anchors:
        if abs(lat - a_lat) > max_dist_deg:
            continue
        _, _, dist = geodesic_deg(lat, lon, a_lat, a_lon)
        if dist < max_dist_deg:
            g = math.exp(-0.5 * (dist / sigma_deg) ** 2)
            if g > g_max:
                g_max = g
            u = g / ((dist * dist + eps_deg * eps_deg) ** 2)
            weights.append((u, a_params))

    if not weights:
        return dict(base_params)

    alpha = max_blend * g_max
    u_sum = sum(u for u, _ in weights)
    blended: dict[str, float] = {}
    for k, base_val in base_params.items():
        anchor_val = sum(u * p[k] for u, p in weights if k in p) / u_sum
        blended[k] = (1.0 - alpha) * base_val + alpha * anchor_val
    return blended
