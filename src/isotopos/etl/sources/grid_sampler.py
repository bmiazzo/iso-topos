"""Vectorized global grid container, raster gap filling, and interpolation provenance tracking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import overload

import numpy as np


@dataclass
class GlobalGrid:
    """Equirectangular 2D scientific raster grid supporting wrapping and bilinear/window sampling."""

    data: np.ndarray
    lat_min: float = -90.0
    lat_max: float = 90.0
    lon_min: float = -180.0
    lon_max: float = 180.0
    origin_top: bool = True
    lon_0_360: bool = False
    interpolated_mask: np.ndarray | None = None

    def __post_init__(self) -> None:
        if self.lon_0_360 and self.lon_min == -180.0 and self.lon_max == 180.0:
            self.lon_min = 0.0
            self.lon_max = 360.0

    @property
    def nrows(self) -> int:
        return int(self.data.shape[0])

    @property
    def ncols(self) -> int:
        return int(self.data.shape[1])

    def _to_pixel_coords(self, lat: float | np.ndarray, lon: float | np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        lat_arr = np.asarray(lat, dtype=np.float64)
        lon_arr = np.asarray(lon, dtype=np.float64)
        if self.lon_0_360:
            lon_norm = np.mod(lon_arr, 360.0)
        else:
            lon_norm = np.mod(lon_arr + 180.0, 360.0) - 180.0

        # Clamp latitude strictly within grid vertical extent
        lat_clamped = np.clip(lat_arr, self.lat_min, self.lat_max)
        lat_span = max(self.lat_max - self.lat_min, 1e-9)
        lon_span = max(self.lon_max - self.lon_min, 1e-9)

        if self.origin_top:
            row_f = (self.lat_max - lat_clamped) / lat_span * self.nrows - 0.5
        else:
            row_f = (lat_clamped - self.lat_min) / lat_span * self.nrows - 0.5
        col_f = (lon_norm - self.lon_min) / lon_span * self.ncols - 0.5
        return row_f, col_f

    @overload
    def sample_nearest(self, lat: float, lon: float) -> float: ...

    @overload
    def sample_nearest(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray: ...

    def sample_nearest(self, lat: float | np.ndarray, lon: float | np.ndarray) -> float | np.ndarray:
        """Nearest-cell lookup with longitudinal wraparound."""
        row_f, col_f = self._to_pixel_coords(lat, lon)
        rows = np.clip(np.rint(row_f).astype(np.int64), 0, self.nrows - 1)
        cols = np.mod(np.rint(col_f).astype(np.int64), self.ncols)
        out = self.data[rows, cols]
        return float(out) if np.ndim(lat) == 0 and np.ndim(lon) == 0 else out

    def sample_nearest_with_provenance(self, lat: float, lon: float) -> tuple[float, bool]:
        """Return (value, was_interpolated) for a single geographic coordinate."""
        row_f, col_f = self._to_pixel_coords(lat, lon)
        row = int(np.clip(np.rint(row_f), 0, self.nrows - 1))
        col = int(np.mod(np.rint(col_f), self.ncols))
        val = float(self.data[row, col])
        interp = False if self.interpolated_mask is None else bool(self.interpolated_mask[row, col])
        return val, interp

    @overload
    def sample_bilinear(self, lat: float, lon: float) -> float: ...

    @overload
    def sample_bilinear(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray: ...

    def sample_bilinear(self, lat: float | np.ndarray, lon: float | np.ndarray) -> float | np.ndarray:
        """Bilinear interpolation ignoring NaN corners gracefully."""
        row_f, col_f = self._to_pixel_coords(lat, lon)
        r0 = np.clip(np.floor(row_f).astype(np.int64), 0, self.nrows - 1)
        r1 = np.clip(r0 + 1, 0, self.nrows - 1)
        dr = np.clip(row_f - r0, 0.0, 1.0)

        c0 = np.mod(np.floor(col_f).astype(np.int64), self.ncols)
        c1 = np.mod(c0 + 1, self.ncols)
        dc = np.mod(col_f - np.floor(col_f), 1.0)

        v00 = self.data[r0, c0]
        v01 = self.data[r0, c1]
        v10 = self.data[r1, c0]
        v11 = self.data[r1, c1]

        w00 = (1.0 - dr) * (1.0 - dc) * np.isfinite(v00)
        w01 = (1.0 - dr) * dc * np.isfinite(v01)
        w10 = dr * (1.0 - dc) * np.isfinite(v10)
        w11 = dr * dc * np.isfinite(v11)

        w_sum = w00 + w01 + w10 + w11
        num = (
            np.where(np.isfinite(v00), v00, 0.0) * w00
            + np.where(np.isfinite(v01), v01, 0.0) * w01
            + np.where(np.isfinite(v10), v10, 0.0) * w10
            + np.where(np.isfinite(v11), v11, 0.0) * w11
        )
        out = np.where(w_sum > 0.0, num / np.maximum(w_sum, 1e-12), np.nan)
        return float(out) if np.ndim(lat) == 0 and np.ndim(lon) == 0 else out

    def sample_window_stats(
        self,
        lats: np.ndarray,
        lons: np.ndarray,
        half_deg: float = 0.25,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Aggregate mean over valid pixels within ±half_deg of each query point + missing flag.

        If no raw pixels inside a query cell's window are valid (and ``interpolated_mask`` is None),
        ``missing_mask[i]`` is True; if ``interpolated_mask`` was already populated during raster
        gap-filling, ``missing_mask[i]`` is True only when ZERO originally measured pixels fall in
        the window.
        """
        lats_a = np.asarray(lats, dtype=np.float64)
        lons_a = np.asarray(lons, dtype=np.float64)
        px_per_deg_lat = self.nrows / max(self.lat_max - self.lat_min, 1e-9)
        px_per_deg_lon = self.ncols / max(self.lon_max - self.lon_min, 1e-9)
        ry = max(0, int(round(half_deg * px_per_deg_lat)))
        rx = max(0, int(round(half_deg * px_per_deg_lon)))

        row_f, col_f = self._to_pixel_coords(lats_a, lons_a)
        rc = np.clip(np.rint(row_f).astype(np.int64), 0, self.nrows - 1)
        cc = np.rint(col_f).astype(np.int64)

        vals_sum = np.zeros(len(lats_a), dtype=np.float64)
        counts = np.zeros(len(lats_a), dtype=np.int64)
        raw_measured_counts = np.zeros(len(lats_a), dtype=np.int64)

        for dr in range(-ry, ry + 1):
            rr = np.clip(rc + dr, 0, self.nrows - 1)
            for dc in range(-rx, rx + 1):
                c_wrap = np.mod(cc + dc, self.ncols)
                v = self.data[rr, c_wrap]
                ok = np.isfinite(v)
                vals_sum += np.where(ok, v, 0.0)
                counts += ok.astype(np.int64)
                if self.interpolated_mask is not None:
                    meas = ok & (~self.interpolated_mask[rr, c_wrap])
                else:
                    meas = ok
                raw_measured_counts += meas.astype(np.int64)

        means = np.where(counts > 0, vals_sum / np.maximum(counts, 1), np.nan)
        was_interpolated = raw_measured_counts == 0
        return means, was_interpolated


def filter_emag2_sentinels(raw_grid: np.ndarray) -> np.ndarray:
    """Convert raw EMAG2v3 magnetic anomaly raster to |ΔB| (nT) with sentinels masked to NaN in float32."""
    arr = np.asarray(raw_grid, dtype=np.float32)
    invalid = (
        ~np.isfinite(arr)
        | (np.abs(arr - 99999.0) < 1e-1)
        | (np.abs(arr + 888.0) < 1e-1)
        | (np.abs(arr + 999.0) < 1e-1)
        | (arr >= 90000.0)
        | (arr <= -50000.0)
    )
    out = np.abs(arr)
    out[invalid] = np.nan
    return out


def fill_raster_gaps_with_mask(
    grid: np.ndarray,
    max_iterations: int = 32,
) -> tuple[np.ndarray, np.ndarray]:
    """Fill NaN track gaps smoothly from neighboring valid cells and track which pixels were filled.

    Uses iterative 8-neighbor diffusion across valid neighbors in float32, followed by coarse-to-fine zonal
    median fallback only if massive oceanic voids still remain after max_iterations.
    """
    arr = np.asarray(grid, dtype=np.float32).copy()
    originally_missing = ~np.isfinite(arr)
    if not originally_missing.any():
        return arr, originally_missing

    if np.isfinite(arr).sum() == 0:
        raise ValueError("Cannot interpolate raster grid with zero finite pixels.")

    # Iterative 8-neighbor valid mean diffusion with longitudinal wraparound
    shifts = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    nan_row = np.full((1, arr.shape[1]), np.nan, dtype=np.float32)
    for _ in range(max_iterations):
        missing = ~np.isfinite(arr)
        if not missing.any():
            break
        acc = np.zeros_like(arr, dtype=np.float32)
        cnt = np.zeros_like(arr, dtype=np.float32)
        for dy, dx in shifts:
            rolled = np.roll(arr, shift=dx, axis=1)
            if dy == -1:
                padded = np.vstack([nan_row, rolled[:-1, :]])
            elif dy == 1:
                padded = np.vstack([rolled[1:, :], nan_row])
            else:
                padded = rolled
            ok = np.isfinite(padded)
            acc += np.where(ok, padded, np.float32(0.0))
            cnt += ok.astype(np.float32)
        fillable = missing & (cnt > 0)
        if not fillable.any():
            break
        arr[fillable] = acc[fillable] / cnt[fillable]

    # Nearest-latitude-band or global fallback for any wide oceanic/polar void beyond max_iterations
    remaining = ~np.isfinite(arr)
    if remaining.any():
        global_med = float(np.nanmedian(arr))
        for r in range(arr.shape[0]):
            if remaining[r].any():
                row_finite = np.isfinite(arr[r])
                fill_val = float(np.median(arr[r, row_finite])) if row_finite.any() else global_med
                arr[r, remaining[r]] = fill_val

    return arr, originally_missing
