"""Decoders for NASA PDS3 binary rasters, ESRI ASCII grids, and geomagnetic spherical harmonics."""

from __future__ import annotations

import gzip
import re
from pathlib import Path
from typing import Any

import numpy as np

from .grid_sampler import GlobalGrid

_PDS_KV_RE = re.compile(r"^\s*([A-Z0-9_:]+)\s*=\s*(.+?)\s*$")
_NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eEdD][-+]?\d+)?")


def _parse_pds_scalar(raw: str) -> Any:
    val = raw.strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1].strip()
    # Strip trailing PDS units such as "60.0 <deg>"
    unit_split = re.sub(r"\s*<[^>]+>\s*$", "", val).strip()
    if re.fullmatch(r"[-+]?\d+", unit_split):
        return int(unit_split)
    if re.fullmatch(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", unit_split):
        return float(unit_split)
    return val


def parse_pds_label(lbl_text: str) -> dict[str, Any]:
    """Parse key PDS3 IMAGE and IMAGE_MAP_PROJECTION scalar attributes from a .lbl string."""
    parsed: dict[str, Any] = {}
    for line in lbl_text.splitlines():
        m = _PDS_KV_RE.match(line)
        if not m:
            continue
        key, raw_val = m.group(1), m.group(2)
        if key in {
            "LINES",
            "LINE_SAMPLES",
            "SAMPLE_TYPE",
            "SAMPLE_BITS",
            "SCALING_FACTOR",
            "OFFSET",
            "MISSING_CONSTANT",
            "MAXIMUM_LATITUDE",
            "MINIMUM_LATITUDE",
            "WESTERNMOST_LONGITUDE",
            "EASTERNMOST_LONGITUDE",
            "CENTER_LONGITUDE",
        }:
            parsed[key] = _parse_pds_scalar(raw_val)
    return parsed


def _pds_numpy_dtype(sample_type: str, sample_bits: int) -> np.dtype[Any]:
    st = str(sample_type).upper()
    if "INTEGER" in st or "INT" in st:
        endian = ">" if ("MSB" in st or "SUN" in st or "MAC" in st) else "<"
        if "UNSIGNED" in st:
            return np.dtype(f"{endian}u{sample_bits // 8}")
        return np.dtype(f"{endian}i{sample_bits // 8}")
    if "REAL" in st or "FLOAT" in st:
        endian = ">" if ("IEEE_REAL" in st or "MSB" in st) and "PC" not in st else "<"
        return np.dtype(f"{endian}f{sample_bits // 8}")
    raise ValueError(f"Unsupported PDS sample format: {sample_type} ({sample_bits} bits)")


def load_pds_raster(img_path: Path, lbl_path: Path) -> GlobalGrid:
    """Load a detached NASA PDS3 .img + .lbl binary raster into a scaled float64 GlobalGrid."""
    meta = parse_pds_label(lbl_path.read_text(encoding="utf-8", errors="replace"))
    lines = int(meta["LINES"])
    samples = int(meta["LINE_SAMPLES"])
    dtype = _pds_numpy_dtype(str(meta["SAMPLE_TYPE"]), int(meta["SAMPLE_BITS"]))
    raw = np.fromfile(img_path, dtype=dtype, count=lines * samples).reshape((lines, samples)).astype(np.float64)

    missing = meta.get("MISSING_CONSTANT")
    if isinstance(missing, (int, float)):
        raw[np.abs(raw - float(missing)) < 1e-6] = np.nan
    raw[~np.isfinite(raw)] = np.nan

    scale = float(meta.get("SCALING_FACTOR", 1.0))
    offset = float(meta.get("OFFSET", 0.0))
    scaled = raw * scale + offset

    west = float(meta.get("WESTERNMOST_LONGITUDE", -180.0))
    east = float(meta.get("EASTERNMOST_LONGITUDE", 180.0))
    center_lon = meta.get("CENTER_LONGITUDE")
    if west >= 359.0 and east <= 1.0:
        west, east = 0.0, 360.0
    is_0_360 = (
        east > 180.5
        or (west >= -0.001 and east > 350.0)
        or (isinstance(center_lon, (int, float)) and abs(float(center_lon) - 180.0) < 1e-3 and west >= 0.0)
    )
    return GlobalGrid(
        data=scaled,
        lat_min=float(meta.get("MINIMUM_LATITUDE", -90.0)),
        lat_max=float(meta.get("MAXIMUM_LATITUDE", 90.0)),
        lon_min=west,
        lon_max=east,
        origin_top=True,
        lon_0_360=is_0_360,
    )


def parse_esri_ascii_grid(text: str) -> GlobalGrid:
    """Decode an ESRI ASCII (.asc) grid with header lines and optional NODATA_value."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    header: dict[str, float] = {}
    data_start = 0
    for idx, ln in enumerate(lines):
        parts = ln.split()
        if len(parts) == 2 and parts[0].lower() in {
            "ncols",
            "nrows",
            "xllcorner",
            "yllcorner",
            "xllcenter",
            "yllcenter",
            "cellsize",
            "nodata_value",
        }:
            header[parts[0].lower()] = float(parts[1])
            data_start = idx + 1
        else:
            break

    ncols = int(header["ncols"])
    nrows = int(header["nrows"])
    cellsize = float(header["cellsize"])
    xll = float(header.get("xllcorner", header.get("xllcenter", -180.0) - 0.5 * cellsize))
    yll = float(header.get("yllcorner", header.get("yllcenter", -90.0) - 0.5 * cellsize))
    nodata = header.get("nodata_value", -9999.0)

    flat_vals = np.fromstring(" ".join(lines[data_start:]), sep=" ", dtype=np.float64)
    arr = flat_vals[: nrows * ncols].reshape((nrows, ncols))
    arr[np.abs(arr - nodata) < 1e-6] = np.nan

    return GlobalGrid(
        data=arr,
        lat_min=yll,
        lat_max=yll + nrows * cellsize,
        lon_min=xll,
        lon_max=xll + ncols * cellsize,
        origin_top=True,
        lon_0_360=False,
    )


def parse_spherical_harmonic_table(
    path: Path,
    max_degree: int = 180,
) -> tuple[float, int, list[tuple[int, int, float, float]]]:
    """Parse gzipped or plain (l, m, g_lm, h_lm) spherical harmonic coefficient tables."""
    if path.suffix == ".gz":
        raw_text = gzip.decompress(path.read_bytes()).decode("utf-8", errors="replace")
    else:
        raw_text = path.read_text(encoding="utf-8", errors="replace")

    lines = raw_text.splitlines()
    # Extract reference radius when encoded on header line (Langlais uses km, Tsunakawa uses meters)
    ref_km = 0.0
    if lines:
        first_nums = _NUM_RE.findall(lines[0].replace(",", " "))
        if first_nums:
            v0 = float(first_nums[0])
            if 1000.0 <= v0 <= 10000.0:
                ref_km = v0
            elif v0 > 1.0e5:
                ref_km = v0 / 1000.0
    for ln in lines[:6]:
        if "ref surface" in ln.lower():
            m = re.search(r"ref\s+surface\s*=\s*([0-9.]+)", ln.lower())
            if m:
                ref_km = float(m.group(1))

    coeffs: list[tuple[int, int, float, float]] = []
    highest_l = 0
    for ln in lines[1:]:
        s = ln.strip()
        if not s or not s[0].isdigit():
            continue
        parts = s.replace(",", " ").split()
        if len(parts) < 3:
            continue
        try:
            degree = int(parts[0])
            order = int(parts[1])
            g = float(parts[2])
            h = float(parts[3]) if len(parts) >= 4 else 0.0
        except ValueError:
            continue
        if degree < 1 or degree > max_degree or order < 0 or order > degree:
            continue
        highest_l = max(highest_l, degree)
        coeffs.append((degree, order, g, h))

    return ref_km, highest_l, coeffs


def eval_spherical_harmonics_mag(
    lats_deg: np.ndarray,
    lons_deg: np.ndarray,
    coeffs: list[tuple[int, int, float, float]],
    ref_radius_km: float,
    alt_km: float = 0.0,
    max_degree: int | None = None,
    field_scale_nt: float = 1.0,
) -> np.ndarray:
    """Compute scalar surface magnetic anomaly |B| (nT) using Schmidt semi-normalized harmonics."""
    lats = np.asarray(lats_deg, dtype=np.float64)
    lons = np.asarray(lons_deg, dtype=np.float64)
    theta = np.deg2rad(90.0 - lats)
    phi = np.deg2rad(lons)
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)

    l_max = max((c[0] for c in coeffs), default=0)
    if max_degree is not None:
        l_max = min(l_max, max_degree)
    if l_max < 1:
        return np.zeros_like(lats, dtype=np.float64)

    g_arr = np.zeros((l_max + 1, l_max + 1), dtype=np.float64)
    h_arr = np.zeros((l_max + 1, l_max + 1), dtype=np.float64)
    for degree, order, g, h in coeffs:
        if 1 <= degree <= l_max and 0 <= order <= degree:
            g_arr[degree, order] = g * field_scale_nt
            h_arr[degree, order] = h * field_scale_nt

    r_ratio = ref_radius_km / max(ref_radius_km + alt_km, 1e-6)
    radial_pow = np.array([r_ratio ** (l + 2) for l in range(l_max + 1)], dtype=np.float64)

    br = np.zeros_like(theta)
    bt = np.zeros_like(theta)
    bp = np.zeros_like(theta)

    # Precompute Schmidt diagonal seed P_{m}^{m}(theta) and dP_{m}^{m}/dtheta without 1/sin(theta)
    p_mm = np.ones_like(theta)
    dp_mm = np.zeros_like(theta)
    w_mm = np.zeros_like(theta)  # P_l^m / sin(theta) for pole-safe B_phi when m >= 1

    for m in range(l_max + 1):
        if m == 1:
            p_mm = sin_t.copy()
            dp_mm = cos_t.copy()
            w_mm = np.ones_like(theta)
        elif m >= 2:
            factor = np.sqrt((2.0 * m - 1.0) / (2.0 * m))
            dp_mm = factor * (cos_t * p_mm + sin_t * dp_mm)
            w_mm = factor * sin_t * w_mm
            p_mm = factor * sin_t * p_mm

        cos_mp = np.cos(m * phi)
        sin_mp = np.sin(m * phi)

        p_prev2 = np.zeros_like(theta)
        dp_prev2 = np.zeros_like(theta)
        w_prev2 = np.zeros_like(theta)
        p_prev1 = p_mm
        dp_prev1 = dp_mm
        w_prev1 = w_mm

        for l in range(m, l_max + 1):
            if l == m:
                p_curr, dp_curr, w_curr = p_mm, dp_mm, w_mm
            elif l == m + 1:
                fac = np.sqrt(2.0 * m + 1.0)
                p_curr = fac * cos_t * p_prev1
                dp_curr = fac * (-sin_t * p_prev1 + cos_t * dp_prev1)
                w_curr = fac * cos_t * w_prev1
            else:
                denom = np.sqrt(float(l * l - m * m))
                c1 = (2.0 * l - 1.0) / denom
                c2 = np.sqrt(float((l - 1) ** 2 - m * m)) / denom
                p_curr = c1 * cos_t * p_prev1 - c2 * p_prev2
                dp_curr = c1 * (-sin_t * p_prev1 + cos_t * dp_prev1) - c2 * dp_prev2
                w_curr = c1 * cos_t * w_prev1 - c2 * w_prev2

            if l >= 1:
                g_lm = g_arr[l, m]
                h_lm = h_arr[l, m]
                if g_lm != 0.0 or h_lm != 0.0:
                    rp = radial_pow[l]
                    gh_cos = g_lm * cos_mp + h_lm * sin_mp
                    br += (l + 1.0) * rp * p_curr * gh_cos
                    bt -= rp * dp_curr * gh_cos
                    if m >= 1:
                        bp += m * rp * w_curr * (g_lm * sin_mp - h_lm * cos_mp)

            p_prev2, p_prev1 = p_prev1, p_curr
            dp_prev2, dp_prev1 = dp_prev1, dp_curr
            w_prev2, w_prev1 = w_prev1, w_curr

    return np.sqrt(br * br + bt * bt + bp * bp)
