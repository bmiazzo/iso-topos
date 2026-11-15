"""Earth open-dataset aggregation (NOAA EMAG2v3, ETOPO2v2c, WorldClim, GLiM, MODIS, Aridity, Obu)."""

from __future__ import annotations

import gc
import io
import math
import warnings
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import tifffile

from ..geodesic_math import compute_grazing_sun_hours
from .baseline_regions import CountryResolver
from .grid_sampler import (
    GlobalGrid,
    fill_raster_gaps_with_mask,
    filter_emag2_sentinels,
)
from .raster_readers import parse_esri_ascii_grid

# GLiM v1.0 numeric ID -> geological composition scores (Hartmann & Moosdorf, 2012)
# 1:su Unconsolidated sediment, 2:vb Basic volcanic (basalt), 3:ss Siliciclastic sedimentary,
# 4:pb Basic plutonic, 5:sm Mixed sedimentary, 6:sc Carbonate sedimentary, 7:va Acid volcanic,
# 8:mt Metamorphic, 9:pa Acid plutonic, 10:vi Intermediate volcanic, 11:wb Water,
# 12:py Pyroclastic, 13:pi Intermediate plutonic, 14:ev Evaporite, 15:nd Nodata, 16:ig Ice/glacier.
_GLIM_BASALT = {
    1: 0.22,
    2: 0.94,
    3: 0.20,
    4: 0.86,
    5: 0.24,
    6: 0.14,
    7: 0.42,
    8: 0.30,
    9: 0.22,
    10: 0.65,
    11: 0.20,
    12: 0.78,
    13: 0.50,
    14: 0.14,
    15: 0.28,
    16: 0.28,
}
_GLIM_ANORTHOSITE = {
    1: 0.22,
    2: 0.22,
    3: 0.26,
    4: 0.74,
    5: 0.24,
    6: 0.18,
    7: 0.48,
    8: 0.64,
    9: 0.72,
    10: 0.42,
    11: 0.20,
    12: 0.30,
    13: 0.78,
    14: 0.12,
    15: 0.30,
    16: 0.34,
}
_GLIM_CLAY_CARB = {
    1: 0.64,
    2: 0.18,
    3: 0.70,
    4: 0.14,
    5: 0.80,
    6: 0.92,
    7: 0.24,
    8: 0.32,
    9: 0.16,
    10: 0.26,
    11: 0.40,
    12: 0.32,
    13: 0.18,
    14: 0.88,
    15: 0.30,
    16: 0.20,
}

# MODIS PFT land-cover classes (Zenodo 6350821: MODIS_Land_Cover_Climatology.CMG05.nc / CMG005)
# 0:Water stays NaN so neighbor land bareness fills coastlines; 1-4:Forests, 5:Shrub, 6:Grass,
# 7-8:Crops, 9:Urban, 10:Snow/Ice, 11:Barren
_MODIS_PFT_BARENESS = {
    1: 0.08,
    2: 0.04,
    3: 0.10,
    4: 0.10,
    5: 0.72,
    6: 0.48,
    7: 0.30,
    8: 0.28,
    9: 0.45,
    10: 0.92,
    11: 0.98,
}


def map_glim_codes_to_scores(codes: np.ndarray) -> dict[str, np.ndarray]:
    """Map GLiM numeric class codes (1..16) to basalt, highland anorthosite, and sediment/clay scores."""
    c_arr = np.asarray(codes, dtype=np.float64)
    basalt = np.full(c_arr.shape, 0.28, dtype=np.float64)
    anorth = np.full(c_arr.shape, 0.30, dtype=np.float64)
    clay = np.full(c_arr.shape, 0.30, dtype=np.float64)
    for code, val in _GLIM_BASALT.items():
        mask = np.isfinite(c_arr) & (np.rint(c_arr) == code)
        basalt[mask] = val
        anorth[mask] = _GLIM_ANORTHOSITE[code]
        clay[mask] = _GLIM_CLAY_CARB[code]
    return {
        "basalt_volcanic_score": basalt,
        "anorthosite_highland_score": anorth,
        "clay_carbonate_sediment_score": clay,
    }


def _mask_gdal_nodata(arr: np.ndarray) -> np.ndarray:
    """Replace non-finite values and extreme float32 GDAL nodata sentinels with NaN."""
    out = arr.astype(np.float32, copy=False)
    out[(~np.isfinite(out)) | (np.abs(out) > 1e15) | (out < -30000.0)] = np.nan
    return out


def _read_tif_safe(raw_bytes: bytes) -> np.ndarray:
    """Decode GeoTIFF bytes and mask GDAL nodata sentinels to NaN."""
    return _mask_gdal_nodata(tifffile.imread(io.BytesIO(raw_bytes)))


def _as_tiff_page(page: tifffile.TiffPage | tifffile.TiffFrame) -> tifffile.TiffPage:
    """Resolve a TiffPage or TiffFrame to a concrete TiffPage so TIFF tags are accessible."""
    if isinstance(page, tifffile.TiffFrame):
        return page.aspage()
    return page


def _read_h5_array(hf: h5py.File, key: str, dtype: Any = np.float64) -> np.ndarray:
    """Read an HDF5 dataset into a typed NumPy array, narrowing group item union types."""
    obj = hf[key]
    if not isinstance(obj, h5py.Dataset):
        raise TypeError(f"Expected HDF5 Dataset for '{key}', got {type(obj).__name__}")
    return np.asarray(obj[()], dtype=dtype)


def _downsample_block_mean(arr: np.ndarray, bh: int, bw: int) -> np.ndarray:
    """Downsample a 2D float32 array by (bh, bw) block nanmean with minimal peak memory."""
    h_crop = (arr.shape[0] // bh) * bh
    w_crop = (arr.shape[1] // bw) * bw
    blocks = arr[:h_crop, :w_crop].reshape(h_crop // bh, bh, w_crop // bw, bw)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(blocks, axis=(1, 3)).astype(np.float32, copy=False)


def _compute_slope_deg_and_relief(
    elev: np.ndarray,
    scale_factor: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute surface slope angle (deg) and normalized micro-roughness (0..1) on a lat/lon DEM."""
    nrows, ncols = elev.shape
    lat_deg = np.linspace(90.0 - 90.0 / nrows, -90.0 + 90.0 / nrows, nrows, dtype=np.float32)
    dlat_m = np.float32(111_195.0 * (180.0 / nrows))
    dlon_m = np.maximum(
        111_195.0 * (360.0 / ncols) * np.cos(np.deg2rad(lat_deg)),
        2_500.0,
    ).astype(np.float32)[:, None]

    # Finite central differences with longitudinal wraparound
    dz_dy_arr = np.asarray(np.gradient(elev, axis=0), dtype=np.float32)
    dz_dy = dz_dy_arr / dlat_m
    dz_dx = (np.roll(elev, -1, axis=1) - np.roll(elev, 1, axis=1)) / (np.float32(2.0) * dlon_m)

    # Downsampled DEM steepness scaled for sub-cell terrain relief representation
    slope_deg = (
        np.rad2deg(np.arctan(np.sqrt(dz_dx * dz_dx + dz_dy * dz_dy))) * np.float32(scale_factor)
    ).astype(np.float32, copy=False)
    del dz_dx, dz_dy, dz_dy_arr

    # Accumulate 4-neighbor elevation dispersion in-place (avoids 4x 2D stack allocation)
    relief_m = np.zeros_like(elev, dtype=np.float32)
    for axis in (0, 1):
        for shift in (-1, 1):
            relief_m += np.abs(np.roll(elev, shift, axis=axis) - elev)
    relief_m *= np.float32(0.25)
    roughness = np.clip(
        np.log1p(np.maximum(relief_m, np.float32(0.0))) / np.float32(np.log1p(650.0)),
        np.float32(0.05),
        np.float32(0.98),
    ).astype(np.float32, copy=False)
    return slope_deg, roughness


def _heal_local_grid_pinholes(
    grid: np.ndarray,
    max_passes: int = 2,
    min_neighbors: int = 2,
) -> np.ndarray:
    """Fill narrow interior NaN bin voids via local 8-neighbor means (never crossing poles)."""
    out = grid.astype(np.float64, copy=True)
    shifts = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))
    nrows = out.shape[0]
    for _ in range(max_passes):
        missing = ~np.isfinite(out)
        if not missing.any():
            break
        valid = np.isfinite(out)
        val_zero = np.where(valid, out, 0.0)
        neigh_sum = np.zeros_like(out)
        neigh_cnt = np.zeros_like(out, dtype=np.int32)
        for dr, dc in shifts:
            shifted_val = np.roll(np.roll(val_zero, shift=dc, axis=1), shift=dr, axis=0)
            shifted_valid = np.roll(np.roll(valid, shift=dc, axis=1), shift=dr, axis=0)
            # Do not wrap North <-> South pole boundaries across latitude axis
            if dr == 1:
                shifted_val[0, :] = 0.0
                shifted_valid[0, :] = False
            elif dr == -1:
                shifted_val[nrows - 1, :] = 0.0
                shifted_valid[nrows - 1, :] = False
            neigh_sum += shifted_val
            neigh_cnt += shifted_valid.astype(np.int32)
        fillable = missing & (neigh_cnt >= min_neighbors)
        if not fillable.any():
            break
        out[fillable] = neigh_sum[fillable] / neigh_cnt[fillable]
    return out


def _regrid_obu_permafrost_to_equirectangular(nc_path: Path) -> GlobalGrid:
    """Bin Obu et al. (2019) polar stereographic PerProb onto a 0.5-deg global grid."""
    with h5py.File(nc_path, "r") as hf:
        lats = _read_h5_array(hf, "latitude", dtype=np.float64)
        lons = _read_h5_array(hf, "longitude", dtype=np.float64)
        pprob = _read_h5_array(hf, "PerProb", dtype=np.float64)

    # Guard against finite fill sentinels (e.g. 1e32) paired with valid/borderline PerProb
    valid = (
        np.isfinite(pprob)
        & (pprob >= 0.0)
        & (pprob <= 1.0)
        & np.isfinite(lats)
        & (lats >= -90.0)
        & (lats <= 90.0)
        & np.isfinite(lons)
        & (lons >= -180.0)
        & (lons <= 360.0)
    )
    res_deg = 0.5
    nlat, nlon = int(180.0 / res_deg), int(360.0 / res_deg)  # 360 x 720
    sums = np.zeros((nlat, nlon), dtype=np.float64)
    counts = np.zeros((nlat, nlon), dtype=np.int64)

    if valid.any():
        vlat = lats[valid]
        vlon = np.mod(lons[valid] + 180.0, 360.0) - 180.0
        vprob = pprob[valid]

        rows = np.clip(np.floor((90.0 - vlat) / res_deg).astype(np.int64), 0, nlat - 1)
        cols = np.mod(np.floor((vlon + 180.0) / res_deg).astype(np.int64), nlon)
        np.add.at(sums, (rows, cols), vprob)
        np.add.at(counts, (rows, cols), 1)

    grid = np.where(counts > 0, sums / np.maximum(counts, 1), np.nan)
    healed = _heal_local_grid_pinholes(grid, max_passes=2, min_neighbors=2)
    return GlobalGrid(data=healed, origin_top=True)


def _load_emag2_grid(tif_path: Path) -> GlobalGrid:
    """Load NOAA EMAG2v3 upward-continued magnetic anomaly GeoTIFF with 3x3 aggregation."""
    with tifffile.TiffFile(tif_path) as tf:
        page = _as_tiff_page(tf.pages[0])
        tie = page.tags.get("ModelTiepointTag")
        x0 = float(tie.value[3]) if tie and len(tie.value) >= 4 else -180.0
        raw_emag = np.asarray(page.asarray(), dtype=np.float32)
    emag_lon_0_360 = x0 > -1.0
    emag_clean = filter_emag2_sentinels(raw_emag)
    del raw_emag
    emag_sub = _downsample_block_mean(emag_clean, 3, 3)
    del emag_clean
    gc.collect()
    emag_filled, emag_gap_mask = fill_raster_gaps_with_mask(emag_sub, max_iterations=48)
    return GlobalGrid(
        data=emag_filled.astype(np.float32, copy=False),
        lat_min=-90.0,
        lat_max=90.0,
        origin_top=True,
        lon_0_360=emag_lon_0_360,
        interpolated_mask=emag_gap_mask,
    )


def _load_etopo_grids(zip_path: Path) -> tuple[GlobalGrid, GlobalGrid, GlobalGrid]:
    """Load ETOPO2v2c int16 elevation binary zip and derive elevation, slope, and roughness grids."""
    with zipfile.ZipFile(zip_path) as zf:
        bin_name = next(n for n in zf.namelist() if n.lower().endswith((".bin", ".raw")))
        raw_bytes = zf.read(bin_name)
    flat = np.frombuffer(raw_bytes, dtype="<i2")
    nrows = math.isqrt(flat.size // 2)
    if flat.size != 2 * nrows * nrows or nrows % 3 != 0:
        raise ValueError(
            f"Expected 2:1 equirectangular int16 ETOPO grid divisible by 3, got {flat.size} samples"
        )
    ncols = 2 * nrows
    etopo_i16 = flat.reshape((nrows, ncols))
    # Downsample 3x3 to 6-arc-min (1800 x 3600 float32, ~25.9 MB) before slope/relief
    elev_6m = etopo_i16.reshape(nrows // 3, 3, ncols // 3, 3).mean(axis=(1, 3), dtype=np.float32)
    del etopo_i16, flat, raw_bytes
    slope_6m, rough_6m = _compute_slope_deg_and_relief(elev_6m, scale_factor=1.85)
    return (
        GlobalGrid(data=elev_6m, origin_top=True),
        GlobalGrid(data=slope_6m, origin_top=True),
        GlobalGrid(data=rough_6m, origin_top=True),
    )


def _load_worldclim_bio_grids(zip_path: Path) -> tuple[GlobalGrid, GlobalGrid, GlobalGrid]:
    """Load WorldClim v2.1 BIO1 (mean temp), BIO2 (diurnal range), and BIO12 (precip) grids."""
    grids: list[GlobalGrid] = []
    with zipfile.ZipFile(zip_path) as zf:
        for tif_name in ("wc2.1_10m_bio_1.tif", "wc2.1_10m_bio_2.tif", "wc2.1_10m_bio_12.tif"):
            raw = _read_tif_safe(zf.read(tif_name))
            filled, mask = fill_raster_gaps_with_mask(raw, max_iterations=18)
            del raw
            grids.append(
                GlobalGrid(
                    data=filled.astype(np.float32, copy=False),
                    origin_top=True,
                    interpolated_mask=mask,
                )
            )
    return grids[0], grids[1], grids[2]


def _load_worldclim_srad_grid(zip_path: Path) -> GlobalGrid:
    """Compute annual normalized clearness index from streaming WorldClim monthly SRAD GeoTIFFs."""
    with zipfile.ZipFile(zip_path) as zf:
        srad_names = sorted(n for n in zf.namelist() if n.endswith(".tif"))
        if not srad_names:
            raise ValueError(f"No .tif monthly bands found inside {zip_path}")
        first = _read_tif_safe(zf.read(srad_names[0]))
        first_valid = np.isfinite(first)
        srad_sum = np.where(first_valid, first, np.float32(0.0)).astype(np.float32, copy=False)
        srad_cnt = first_valid.astype(np.float32)
        del first, first_valid
        for tif_name in srad_names[1:]:
            band = _read_tif_safe(zf.read(tif_name))
            valid = np.isfinite(band)
            srad_sum += np.where(valid, band, np.float32(0.0))
            srad_cnt += valid.astype(np.float32)
            del band, valid
    srad_annual = np.where(srad_cnt > 0, srad_sum / np.maximum(srad_cnt, np.float32(1.0)), np.nan)
    del srad_sum, srad_cnt
    # Annual terrestrial solar radiation spans ~3500 (polar) to ~24500 kJ/m2/day (Atacama/Sahara)
    solar_norm = np.clip(
        (srad_annual.astype(np.float32, copy=False) - np.float32(2200.0)) / np.float32(22500.0),
        np.float32(0.06),
        np.float32(0.96),
    )
    del srad_annual
    solar_f, solar_mask = fill_raster_gaps_with_mask(solar_norm, max_iterations=18)
    return GlobalGrid(
        data=solar_f.astype(np.float32, copy=False),
        origin_top=True,
        interpolated_mask=solar_mask,
    )


def _load_aridity_grid(tif_path: Path) -> GlobalGrid:
    """Load Global Aridity Index GeoTIFF, infer southern bound, and fill coastal/polar gaps."""
    lat_max = 90.0
    with tifffile.TiffFile(tif_path) as tf:
        page = _as_tiff_page(tf.pages[0])
        tie = page.tags.get("ModelTiepointTag")
        scale = page.tags.get("ModelPixelScaleTag")
        ar_raw = _mask_gdal_nodata(np.asarray(page.asarray(), dtype=np.float32))
        nrows, ncols = ar_raw.shape
        if scale and len(scale.value) >= 2 and float(scale.value[1]) > 0.0:
            if tie and len(tie.value) >= 5:
                lat_max = float(tie.value[4])
            ar_lat_min = max(-90.0, round(lat_max - nrows * float(scale.value[1]), 2))
        else:
            ar_lat_min = -60.0 if (nrows / max(ncols, 1)) < 0.46 else -90.0
    if nrows >= 3000:
        ar_raw = _downsample_block_mean(ar_raw, 2, 2)
    ar_fill, ar_mask = fill_raster_gaps_with_mask(ar_raw, max_iterations=16)
    return GlobalGrid(
        data=ar_fill,
        lat_min=ar_lat_min,
        lat_max=lat_max,
        origin_top=True,
        interpolated_mask=ar_mask,
    )


def _load_modis_bareness_grid(zip_path: Path) -> GlobalGrid:
    """Load MODIS CMG005 landcover climatology HDF5 and derive surface bareness fraction."""
    with zipfile.ZipFile(zip_path) as zf:
        nc_name = next(n for n in zf.namelist() if "CMG005" in n and n.endswith(".nc"))
        lc_bytes = zf.read(nc_name)
    with h5py.File(io.BytesIO(lc_bytes), "r") as hf:
        pft_raw = _read_h5_array(hf, "landcover_PFT", dtype=np.float32)
        # Zenodo CMG005 stores transposed (lon, lat) and often has zeroed NetCDF dimension scales
        if pft_raw.shape[0] > pft_raw.shape[1]:
            pft_raw = pft_raw.T
        if "latitude" in hf:
            lat_vec = _read_h5_array(hf, "latitude", dtype=np.float64)
            if (
                lat_vec.size >= 2
                and np.isfinite(lat_vec[0])
                and np.isfinite(lat_vec[-1])
                and float(lat_vec[0]) < float(lat_vec[-1])
            ):
                pft_raw = np.flipud(pft_raw)
    del lc_bytes
    bare_arr = np.full(pft_raw.shape, np.nan, dtype=np.float32)
    pft_int = np.rint(pft_raw)
    del pft_raw
    for cls_id, b_val in _MODIS_PFT_BARENESS.items():
        bare_arr[pft_int == cls_id] = np.float32(b_val)
    del pft_int
    bare_sub = _downsample_block_mean(bare_arr, 2, 2)
    del bare_arr
    bare_f, _ = fill_raster_gaps_with_mask(bare_sub, max_iterations=12)
    return GlobalGrid(data=bare_f, origin_top=True)


def _load_glim_grid(zip_path: Path) -> GlobalGrid:
    """Load GLiM v1.0 0.5-deg global lithology ESRI ASCII grid."""
    with zipfile.ZipFile(zip_path) as zf:
        asc_name = next(n for n in zf.namelist() if n.endswith(".asc"))
        asc_text = zf.read(asc_name).decode("utf-8", errors="replace")
    glim_parsed = parse_esri_ascii_grid(asc_text)
    glim_f, _ = fill_raster_gaps_with_mask(glim_parsed.data, max_iterations=10)
    return GlobalGrid(data=np.rint(glim_f), origin_top=True)


@dataclass
class EarthOpenDatasets:
    """Loaded open-dataset grids ready for fast vectorized H3 & hotspot extraction."""

    elev_grid: GlobalGrid
    slope_grid: GlobalGrid
    roughness_grid: GlobalGrid
    emag2_grid: GlobalGrid
    temp_mean_grid: GlobalGrid
    diurnal_range_grid: GlobalGrid
    precip_grid: GlobalGrid
    solar_clearness_grid: GlobalGrid
    aridity_grid: GlobalGrid
    bareness_grid: GlobalGrid
    glim_grid: GlobalGrid
    obu_permafrost_grid: GlobalGrid
    country_resolver: CountryResolver

    @classmethod
    def from_raw_dir(cls, raw_dir: Path) -> "EarthOpenDatasets":
        """Load and pre-aggregate all real Earth datasets from raw_dir into memory-lean grids."""
        earth_dir = raw_dir / "earth"

        emag2_grid = _load_emag2_grid(earth_dir / "emag2_v3_upcont.tif")
        gc.collect()

        elev_grid, slope_grid, roughness_grid = _load_etopo_grids(
            earth_dir / "etopo2v2c_i2_lsb.zip"
        )
        gc.collect()

        temp_mean_grid, diurnal_range_grid, precip_grid = _load_worldclim_bio_grids(
            earth_dir / "wc2.1_10m_bio.zip"
        )
        gc.collect()

        solar_clearness_grid = _load_worldclim_srad_grid(earth_dir / "wc2.1_10m_srad.zip")
        gc.collect()

        aridity_grid = _load_aridity_grid(earth_dir / "global_aridity_2017.tif")
        gc.collect()

        bareness_grid = _load_modis_bareness_grid(earth_dir / "modis_landcover.zip")
        gc.collect()

        glim_grid = _load_glim_grid(earth_dir / "glim_05deg.zip")
        obu_permafrost_grid = _regrid_obu_permafrost_to_equirectangular(
            earth_dir / "obu_permafrost_25km.nc"
        )
        country_resolver = CountryResolver(raw_dir / "ne_50m_admin_0_countries.geojson")

        return cls(
            elev_grid=elev_grid,
            slope_grid=slope_grid,
            roughness_grid=roughness_grid,
            emag2_grid=emag2_grid,
            temp_mean_grid=temp_mean_grid,
            diurnal_range_grid=diurnal_range_grid,
            precip_grid=precip_grid,
            solar_clearness_grid=solar_clearness_grid,
            aridity_grid=aridity_grid,
            bareness_grid=bareness_grid,
            glim_grid=glim_grid,
            obu_permafrost_grid=obu_permafrost_grid,
            country_resolver=country_resolver,
        )

    def extract_batch(
        self,
        lats: np.ndarray,
        lons: np.ndarray,
    ) -> tuple[list[dict[str, float]], list[list[str]], list[str], list[str]]:
        """Extract all 17 Earth physical parameters, interpolation flags, and country/region tags."""
        n = len(lats)
        elev_m, _ = self.elev_grid.sample_window_stats(lats, lons, half_deg=0.22)
        slope_raw, _ = self.slope_grid.sample_window_stats(lats, lons, half_deg=0.22)
        rough_raw, _ = self.roughness_grid.sample_window_stats(lats, lons, half_deg=0.22)

        emag_nt, emag_interp = self.emag2_grid.sample_window_stats(lats, lons, half_deg=0.35)
        mean_t, temp_interp = self.temp_mean_grid.sample_window_stats(lats, lons, half_deg=0.20)
        diurnal_c, diurn_interp = self.diurnal_range_grid.sample_window_stats(lats, lons, half_deg=0.20)
        precip_mm, precip_interp = self.precip_grid.sample_window_stats(lats, lons, half_deg=0.20)
        solar_wc, solar_interp = self.solar_clearness_grid.sample_window_stats(lats, lons, half_deg=0.20)
        ai_p_pet, ar_interp = self.aridity_grid.sample_window_stats(lats, lons, half_deg=0.20)

        bare_modis = self.bareness_grid.sample_bilinear(lats, lons)
        glim_codes = self.glim_grid.sample_nearest(lats, lons)
        glim_scores = map_glim_codes_to_scores(glim_codes)

        # Combine Northern Hemisphere Obu 2019 permafrost with Southern/alpine cold-climate cryosphere
        obu_raw = self.obu_permafrost_grid.sample_bilinear(lats, lons)
        obu_valid = np.where(np.isfinite(obu_raw), obu_raw, 0.0)
        alpine_polar_cryo = np.clip((1.0 - np.clip((mean_t + 1.5) / 5.5, 0.0, 1.0)), 0.0, 1.0)
        ice_glacier_bonus = np.where(np.rint(glim_codes) == 16, 0.85, 0.0)
        subsurface_ice = np.where(
            (lats >= 45.0) & np.isfinite(obu_raw),
            np.maximum(obu_valid, alpine_polar_cryo * 0.75),
            np.maximum(alpine_polar_cryo, ice_glacier_bonus),
        )
        subsurface_ice = np.clip(subsurface_ice, 0.0, 1.0)

        # Aridity dryness index (0..1): hyper-arid P/PET < 0.05 -> ~0.95+, humid > 1.2 -> < 0.2
        aridity_dryness = np.clip(1.0 / (1.0 + np.maximum(ai_p_pet, 0.0) / 0.28), 0.02, 0.99)
        # Supplement polar/cold deserts (P < 200mm) where PET approaches zero
        polar_dry = np.where(
            (mean_t < -15.0) & (precip_mm < 220.0),
            np.clip(0.75 + 0.20 * (1.0 - np.clip(precip_mm / 220.0, 0.0, 1.0)), 0.72, 0.96),
            0.0,
        )
        aridity_dryness = np.maximum(aridity_dryness, polar_dry)

        # Slope / roughness (ETOPO2 2-arc-min smoothed cell slopes scaled cleanly to deg & [0..1])
        slope_deg = np.clip(slope_raw * 1.4, 0.2, 42.0)
        roughness = np.clip(rough_raw, 0.04, 0.98)

        # Exposed rock/regolith vs soil mantle: barren land + steep relief + lack of glacier ice
        regolith_rock = np.clip(
            0.55 * bare_modis + 0.30 * roughness + 0.15 * aridity_dryness,
            0.05,
            0.96,
        )

        # Cold trap / low sublimation loss: requires both cold temp (< -5C) & moisture/dry stability
        cold_trap = np.clip(
            (1.0 - np.clip((mean_t + 12.0) / 14.0, 0.0, 1.0))
            * (0.55 + 0.45 * subsurface_ice),
            0.0,
            0.96,
        )

        # Solar illumination & high-latitude astronomical low-sun grazing hours
        solar_frac = np.clip(solar_wc * (0.85 + 0.15 * aridity_dryness), 0.08, 0.96)
        low_sun_hrs = np.array(
            [compute_grazing_sun_hours(float(lat), obliquity_deg=23.44) for lat in lats],
            dtype=np.float64,
        )

        # Regional macro proxies for sub-grid analog exploration scores (no hotspot smearing)
        basalt_s = glim_scores["basalt_volcanic_score"]
        anorth_s = glim_scores["anorthosite_highland_score"]
        clay_s = glim_scores["clay_carbonate_sediment_score"]
        cave_macro = np.clip(
            0.42 * np.where(np.isin(np.rint(glim_codes), [2, 6, 12]), 0.75, 0.22)
            + 0.25 * roughness
            + 0.15 * np.where(np.rint(glim_codes) == 6, 0.85, 0.20),
            0.05,
            0.82,
        )
        biosig_macro = np.clip(
            0.38 * aridity_dryness
            + 0.28 * subsurface_ice
            + 0.20 * bare_modis
            + 0.14 * clay_s,
            0.05,
            0.90,
        )

        params_list: list[dict[str, float]] = []
        interp_list: list[list[str]] = []
        countries: list[str] = []
        regions: list[str] = []

        for i in range(n):
            d = {
                "elevation_m": round(float(elev_m[i]), 2),
                "slope_deg": round(float(slope_deg[i]), 2),
                "roughness_index": round(float(roughness[i]), 4),
                "anorthosite_highland_score": round(float(anorth_s[i]), 4),
                "basalt_volcanic_score": round(float(basalt_s[i]), 4),
                "clay_carbonate_sediment_score": round(float(clay_s[i]), 4),
                "regolith_rock_abundance": round(float(regolith_rock[i]), 4),
                "magnetic_anomaly_nt": round(float(max(0.0, emag_nt[i])), 2),
                "mean_temp_c": round(float(mean_t[i]), 2),
                "diurnal_amplitude_c": round(float(diurnal_c[i]), 2),
                "solar_illumination_frac": round(float(solar_frac[i]), 4),
                "low_sun_grazing_hours": round(float(low_sun_hrs[i]), 1),
                "aridity_dryness_index": round(float(aridity_dryness[i]), 4),
                "subsurface_ice_permafrost": round(float(subsurface_ice[i]), 4),
                "cold_trap_sublimation_index": round(float(cold_trap[i]), 4),
                "subsurface_cave_drilling_score": round(float(cave_macro[i]), 4),
                "biosignature_preservation_score": round(float(biosig_macro[i]), 4),
            }
            params_list.append(d)

            interps: list[str] = []
            if bool(emag_interp[i]):
                interps.append("magnetic_anomaly_nt")
            if bool(temp_interp[i]):
                interps.append("mean_temp_c")
            if bool(diurn_interp[i]):
                interps.append("diurnal_amplitude_c")
            if bool(solar_interp[i]):
                interps.append("solar_illumination_frac")
            if bool(ar_interp[i]) or bool(precip_interp[i]):
                interps.append("aridity_dryness_index")
            interp_list.append(interps)

            c_name, r_name = self.country_resolver.resolve(float(lats[i]), float(lons[i]))
            countries.append(c_name)
            regions.append(r_name)

        return params_list, interp_list, countries, regions
