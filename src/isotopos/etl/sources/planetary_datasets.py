"""Moon and Mars open-dataset extraction (LRO LOLA/Diviner, LP GRS, MGS MOLA/TES, Odyssey GRS, MAG SH)."""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..geodesic_math import compute_grazing_sun_hours
from .grid_sampler import GlobalGrid, fill_raster_gaps_with_mask
from .raster_readers import (
    eval_spherical_harmonics_mag,
    load_pds_raster,
    parse_spherical_harmonic_table,
)


def _downsample_block_mean(
    arr: np.ndarray,
    target_rows: int,
    target_cols: int,
) -> np.ndarray:
    """Block-average divisible high-res grids down to <= (target_rows, target_cols)."""
    nrows, ncols = arr.shape
    if nrows <= target_rows and ncols <= target_cols:
        return np.asarray(arr, dtype=np.float64)
    if nrows % target_rows == 0 and ncols % target_cols == 0:
        rf = nrows // target_rows
        cf = ncols // target_cols
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return np.nanmean(arr.reshape(target_rows, rf, target_cols, cf), axis=(1, 3))
    return np.asarray(arr, dtype=np.float64)


def _compute_planet_slope_deg(elev_m: np.ndarray, radius_m: float) -> np.ndarray:
    nrows, ncols = elev_m.shape
    lat_deg = np.linspace(90.0 - 90.0 / nrows, -90.0 + 90.0 / nrows, nrows)
    dy = radius_m * np.deg2rad(180.0 / nrows)
    dx = np.maximum(radius_m * np.deg2rad(360.0 / ncols) * np.cos(np.deg2rad(lat_deg)), 2000.0)[:, None]
    dz_dy = np.gradient(elev_m, axis=0) / dy
    dz_dx = (np.roll(elev_m, -1, axis=1) - np.roll(elev_m, 1, axis=1)) / (2.0 * dx)
    return np.rad2deg(np.arctan(np.sqrt(dz_dx * dz_dx + dz_dy * dz_dy)))


def _parse_odyssey_grs_table(tab_path: Path) -> GlobalGrid:
    """Parse 5x5 deg Odyssey GRS table (columns: lat, lon[0..360], conc, ...; missing=9999.999)."""
    rows_lat: list[float] = []
    rows_lon: list[float] = []
    rows_val: list[float] = []
    for ln in tab_path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = ln.split()
        if len(parts) < 3:
            continue
        try:
            lat = float(parts[0])
            lon = float(parts[1])
            val = float(parts[2])
        except ValueError:
            continue
        rows_lat.append(lat)
        rows_lon.append(lon)
        rows_val.append(np.nan if abs(val) >= 9000.0 else val)

    # Grid is 36 lat rows (-87.5..+87.5) x 72 lon cols (2.5..357.5)
    grid = np.full((36, 72), np.nan, dtype=np.float64)
    for lat, lon, val in zip(rows_lat, rows_lon, rows_val):
        r = int(np.clip(np.floor((87.5 - lat) / 5.0 + 0.5), 0, 35))
        c = int(np.mod(np.floor(lon / 5.0), 72))
        grid[r, c] = val

    filled, _ = fill_raster_gaps_with_mask(grid, max_iterations=16)
    return GlobalGrid(data=filled, origin_top=True, lon_0_360=True)


def _parse_lp_grs_table(tab_path: Path) -> dict[str, GlobalGrid]:
    """Parse Lunar Prospector GRS 2-deg elemental abundance table (W_AL2O3, W_FEO, W_TIO2 in g/g -> wt%, NEUTRON_DEN)."""
    # Column indices from lpgrs_high1_elem_abundance_2deg.lbl (0-based):
    # 1:MIN_LAT, 2:MAX_LAT, 3:MIN_LON, 4:MAX_LON, 6:NEUTRON_DEN, 8:W_AL2O3(g/g), 11:W_TIO2(g/g), 12:W_FEO(g/g)
    nlat, nlon = 90, 180
    grids = {k: np.full((nlat, nlon), np.nan, dtype=np.float64) for k in ("neutron", "al2o3", "tio2", "feo")}
    scales = {"neutron": 1.0, "al2o3": 100.0, "tio2": 100.0, "feo": 100.0}
    for ln in tab_path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = ln.split()
        if len(parts) < 15:
            continue
        try:
            min_lat = float(parts[1])
            max_lat = float(parts[2])
            min_lon = float(parts[3])
            max_lon = float(parts[4])
            r_hi = int(np.clip(np.floor((90.0 - min_lat) / 2.0), 0, nlat))
            r_lo = int(np.clip(np.floor((90.0 - max_lat) / 2.0), 0, nlat - 1))
            if r_hi <= r_lo:
                r_hi = min(nlat, r_lo + 1)
            c_span = max(1, int(round((max_lon - min_lon) / 2.0)))
            c0 = int(np.floor((min_lon + 180.0) / 2.0)) % nlon
            cols = [(c0 + dc) % nlon for dc in range(min(nlon, c_span))]
            for key, col_idx in (("neutron", 6), ("al2o3", 8), ("tio2", 11), ("feo", 12)):
                v = float(parts[col_idx]) * scales[key]
                if abs(v) < 1e6 and v > -900.0:
                    grids[key][r_lo:r_hi, cols] = v
        except ValueError:
            continue

    out: dict[str, GlobalGrid] = {}
    for key, arr in grids.items():
        filled, _ = fill_raster_gaps_with_mask(arr, max_iterations=16)
        out[key] = GlobalGrid(data=filled, origin_top=True, lon_0_360=False)
    return out


@dataclass
class MoonOpenDatasets:
    """Real LRO LOLA, Diviner, Lunar Prospector GRS, and Tsunakawa (2015) magnetic datasets."""

    elev_grid: GlobalGrid
    slope_grid: GlobalGrid
    rough_grid: GlobalGrid
    rock_abund_grid: GlobalGrid
    diviner_st_grid: GlobalGrid
    lp_grs_grids: dict[str, GlobalGrid]
    mag_ref_km: float
    mag_coeffs: list[tuple[int, int, float, float]]

    @classmethod
    def from_raw_dir(cls, raw_dir: Path) -> "MoonOpenDatasets":
        mdir = raw_dir / "moon"
        # LRO LOLA shape/radius -> elevation above 1737.4 km reference sphere
        ldem = load_pds_raster(mdir / "ldem_4.img", mdir / "ldem_4.lbl")
        # ldem scaling converts DN to km or m; ensure elevation_m has mean ~0..±10000 m
        if np.nanmean(np.abs(ldem.data)) < 50.0:
            ldem.data = ldem.data * 1000.0
        elif np.nanmedian(ldem.data) > 100000.0:
            ldem.data = ldem.data - 1_737_400.0

        # Downsample 16ppd LDSM/LDRM by 4x to crisp 4ppd (720 x 1440) when larger
        ldsm_raw = load_pds_raster(mdir / "ldsm_16.img", mdir / "ldsm_16.lbl")
        ldrm_raw = load_pds_raster(mdir / "ldrm_16.img", mdir / "ldrm_16.lbl")
        ldsm_4 = _downsample_block_mean(ldsm_raw.data, 720, 1440)
        ldrm_4 = _downsample_block_mean(ldrm_raw.data, 720, 1440)
        ldsm_f, _ = fill_raster_gaps_with_mask(ldsm_4, max_iterations=12)
        ldrm_f, _ = fill_raster_gaps_with_mask(ldrm_4, max_iterations=12)

        # Diviner 32ppd (-60..+60) -> downsample 8x to 4ppd (480 x 1440) within -60..+60
        ra_raw = load_pds_raster(mdir / "dgdr_ra_avg_cyl_032_img.img", mdir / "dgdr_ra_avg_cyl_032_img.lbl")
        st_raw = load_pds_raster(mdir / "dgdr_st_avg_cyl_032_img.img", mdir / "dgdr_st_avg_cyl_032_img.lbl")
        ra_4 = _downsample_block_mean(ra_raw.data, 480, 1440)
        st_4 = _downsample_block_mean(st_raw.data, 480, 1440)
        ra_f, _ = fill_raster_gaps_with_mask(ra_4, max_iterations=12)
        st_f, _ = fill_raster_gaps_with_mask(st_4, max_iterations=12)

        lp_grids = _parse_lp_grs_table(mdir / "lpgrs_high1_elem_abundance_2deg.tab")
        ref_km, _, coeffs = parse_spherical_harmonic_table(mdir / "T2015_449.sh.gz", max_degree=120)
        if ref_km <= 0.0:
            ref_km = 1737.4

        return cls(
            elev_grid=ldem,
            slope_grid=GlobalGrid(data=ldsm_f, origin_top=True, lon_0_360=ldsm_raw.lon_0_360),
            rough_grid=GlobalGrid(data=ldrm_f, origin_top=True, lon_0_360=ldrm_raw.lon_0_360),
            rock_abund_grid=GlobalGrid(data=ra_f, lat_min=-60.0, lat_max=60.0, lon_min=0.0, lon_max=360.0, origin_top=True, lon_0_360=True),
            diviner_st_grid=GlobalGrid(data=st_f, lat_min=-60.0, lat_max=60.0, lon_min=0.0, lon_max=360.0, origin_top=True, lon_0_360=True),
            lp_grs_grids=lp_grids,
            mag_ref_km=ref_km,
            mag_coeffs=coeffs,
        )

    def extract_batch(self, lats: np.ndarray, lons: np.ndarray) -> list[dict[str, float]]:
        elev_m = np.asarray(self.elev_grid.sample_bilinear(lats, lons), dtype=np.float64)
        slope_deg = np.clip(np.asarray(self.slope_grid.sample_bilinear(lats, lons), dtype=np.float64), 0.1, 45.0)
        rough_m = np.asarray(self.rough_grid.sample_bilinear(lats, lons), dtype=np.float64)
        roughness = np.clip(rough_m / max(float(np.nanpercentile(self.rough_grid.data, 98)), 1.0), 0.12, 0.96)

        ra = np.asarray(self.rock_abund_grid.sample_bilinear(lats, lons), dtype=np.float64)
        st_dev = np.asarray(self.diviner_st_grid.sample_bilinear(lats, lons), dtype=np.float64)
        polar_blend = np.clip((np.abs(lats) - 60.0) / 30.0, 0.0, 1.0)
        rock_abund = np.clip(0.65 + 0.30 * np.clip(ra / 0.08, 0.0, 1.0) * (1.0 - polar_blend) + 0.25 * roughness, 0.45, 0.97)

        feo = np.asarray(self.lp_grs_grids["feo"].sample_bilinear(lats, lons), dtype=np.float64)
        tio2 = np.asarray(self.lp_grs_grids["tio2"].sample_bilinear(lats, lons), dtype=np.float64)
        al2o3 = np.asarray(self.lp_grs_grids["al2o3"].sample_bilinear(lats, lons), dtype=np.float64)
        neutron = np.asarray(self.lp_grs_grids["neutron"].sample_bilinear(lats, lons), dtype=np.float64)

        # Maria basalt (FeO ~14-22%, TiO2 ~2-10%) vs Feldspathic Highlands (Al2O3 ~24-30%, FeO ~3-6%)
        basalt = np.clip((feo - 3.5) / 14.5 + 0.15 * np.clip(tio2 / 6.0, 0.0, 1.0), 0.04, 0.96)
        anorth = np.clip(0.30 + 0.68 * np.clip((al2o3 - 14.0) / 16.0, 0.0, 1.0) * (1.0 - 0.55 * basalt), 0.10, 0.98)

        # Tsunakawa 2015 magnetic model coefficients are in Teslas -> * 1e9 converts to nT
        mag_nt = eval_spherical_harmonics_mag(
            lats_deg=lats,
            lons_deg=lons,
            coeffs=self.mag_coeffs,
            ref_radius_km=self.mag_ref_km,
            alt_km=5.0,
            max_degree=120,
            field_scale_nt=1.0e9,
        )

        # Radiometric lunar thermal regime modulated by real Diviner rock/nighttime variation + latitude
        cos_l = np.cos(np.deg2rad(np.clip(lats, -89.5, 89.5)))
        mean_temp_c = -158.0 + 138.0 * (cos_l ** 0.55) + np.where(np.abs(lats) < 60.0, np.clip(st_dev * 0.25, -15.0, 18.0), 0.0)
        diurnal_amp = np.clip(55.0 + 215.0 * (cos_l ** 0.70) - 35.0 * np.clip(ra / 0.1, 0.0, 0.5), 35.0, 290.0)

        # Lower LP epithermal neutron flux + polar cold trap indicates H/ice enhancement
        n_p10, n_p90 = float(np.nanpercentile(self.lp_grs_grids["neutron"].data, 10)), float(np.nanpercentile(self.lp_grs_grids["neutron"].data, 90))
        neutron_deficit = np.clip((n_p90 - neutron) / max(n_p90 - n_p10, 1e-3), 0.0, 1.0)
        polar_cold = np.clip((np.abs(lats) - 70.0) / 20.0, 0.0, 1.0)
        subsurface_ice = np.clip(0.75 * polar_cold * (0.45 + 0.55 * neutron_deficit) + 0.05 * neutron_deficit, 0.01, 0.92)
        cold_trap = np.clip(polar_cold * (0.65 + 0.30 * roughness) + np.clip((-110.0 - mean_temp_c) / 60.0, 0.0, 0.35), 0.02, 0.98)

        solar_frac = np.clip(0.50 + 0.32 * polar_cold * (elev_m / 6000.0 + 0.15), 0.18, 0.92)
        low_sun_hrs = np.array(
            [compute_grazing_sun_hours(float(lat), obliquity_deg=1.54) for lat in lats],
            dtype=np.float64,
        )
        cave_score = np.clip(0.55 * basalt + 0.25 * (slope_deg / 30.0) + 0.10, 0.10, 0.90)

        out: list[dict[str, float]] = []
        for i in range(len(lats)):
            out.append(
                {
                    "elevation_m": round(float(elev_m[i]), 2),
                    "slope_deg": round(float(slope_deg[i]), 2),
                    "roughness_index": round(float(roughness[i]), 4),
                    "anorthosite_highland_score": round(float(anorth[i]), 4),
                    "basalt_volcanic_score": round(float(basalt[i]), 4),
                    "clay_carbonate_sediment_score": 0.0,
                    "regolith_rock_abundance": round(float(rock_abund[i]), 4),
                    "magnetic_anomaly_nt": round(float(mag_nt[i]), 2),
                    "mean_temp_c": round(float(mean_temp_c[i]), 2),
                    "diurnal_amplitude_c": round(float(diurnal_amp[i]), 2),
                    "solar_illumination_frac": round(float(solar_frac[i]), 4),
                    "low_sun_grazing_hours": round(float(low_sun_hrs[i]), 1),
                    "aridity_dryness_index": 1.0,
                    "subsurface_ice_permafrost": round(float(subsurface_ice[i]), 4),
                    "cold_trap_sublimation_index": round(float(cold_trap[i]), 4),
                    "subsurface_cave_drilling_score": round(float(cave_score[i]), 4),
                    "biosignature_preservation_score": 0.0,
                }
            )
        return out


@dataclass
class MarsOpenDatasets:
    """Real MGS MOLA, MGS TES Albedo & Thermal Inertia, Odyssey GRS, and Langlais (2019) SH mag."""

    elev_grid: GlobalGrid
    slope_grid: GlobalGrid
    albedo_grid: GlobalGrid
    ti_night_grid: GlobalGrid
    grs_h2o: GlobalGrid
    grs_fe: GlobalGrid
    grs_si: GlobalGrid
    grs_cl: GlobalGrid
    mag_ref_km: float
    mag_coeffs: list[tuple[int, int, float, float]]

    @classmethod
    def from_raw_dir(cls, raw_dir: Path) -> "MarsOpenDatasets":
        mdir = raw_dir / "mars"
        mola = load_pds_raster(mdir / "megt90n000cb.img", mdir / "megt90n000cb.lbl")
        slope_arr = _compute_planet_slope_deg(mola.data, radius_m=3_396_000.0)
        slope_grid = GlobalGrid(data=slope_arr, origin_top=True, lon_0_360=mola.lon_0_360)

        alb_raw = load_pds_raster(mdir / "global_albedo_8ppd.img", mdir / "global_albedo_8ppd.lbl")
        alb_valid = np.where((alb_raw.data >= 0.01) & (alb_raw.data <= 0.65), alb_raw.data, np.nan)
        alb_mean = _downsample_block_mean(alb_valid, 720, 1440)
        alb_f, _ = fill_raster_gaps_with_mask(alb_mean, max_iterations=16)
        albedo_grid = GlobalGrid(data=alb_f, origin_top=True, lon_0_360=alb_raw.lon_0_360)

        ti_raw = load_pds_raster(mdir / "global_ti_night_2007.img", mdir / "global_ti_night_2007.lbl")
        # 3600x7200 -> 5x5 downsample to 720x1440 (4ppd) when larger
        ti_clean = np.where((ti_raw.data >= 10.0) & (ti_raw.data <= 2500.0), ti_raw.data, np.nan)
        ti_4 = _downsample_block_mean(ti_clean, 720, 1440)
        ti_f, _ = fill_raster_gaps_with_mask(ti_4, max_iterations=16)
        ti_grid = GlobalGrid(data=ti_f, origin_top=True, lon_0_360=ti_raw.lon_0_360)

        grs_h2o = _parse_odyssey_grs_table(mdir / "h2o_sr_5x5.tab")
        grs_fe = _parse_odyssey_grs_table(mdir / "fe_sr_5x5.tab")
        grs_si = _parse_odyssey_grs_table(mdir / "si_sr_5x5.tab")
        grs_cl = _parse_odyssey_grs_table(mdir / "cl_sr_5x5.tab")

        ref_km, _, coeffs = parse_spherical_harmonic_table(mdir / "Langlais2019.sh.gz", max_degree=134)
        if ref_km <= 0.0:
            ref_km = 3393.5

        return cls(
            elev_grid=mola,
            slope_grid=slope_grid,
            albedo_grid=albedo_grid,
            ti_night_grid=ti_grid,
            grs_h2o=grs_h2o,
            grs_fe=grs_fe,
            grs_si=grs_si,
            grs_cl=grs_cl,
            mag_ref_km=ref_km,
            mag_coeffs=coeffs,
        )

    def extract_batch(self, lats: np.ndarray, lons: np.ndarray) -> list[dict[str, float]]:
        elev_m = np.asarray(self.elev_grid.sample_bilinear(lats, lons), dtype=np.float64)
        slope_deg = np.clip(np.asarray(self.slope_grid.sample_bilinear(lats, lons), dtype=np.float64) * 3.0, 0.2, 36.0)
        alb = np.clip(np.asarray(self.albedo_grid.sample_bilinear(lats, lons), dtype=np.float64), 0.08, 0.45)
        ti = np.clip(np.asarray(self.ti_night_grid.sample_bilinear(lats, lons), dtype=np.float64), 30.0, 900.0)

        h2o_pct = np.clip(np.asarray(self.grs_h2o.sample_bilinear(lats, lons), dtype=np.float64), 0.5, 65.0)
        fe_pct = np.clip(np.asarray(self.grs_fe.sample_bilinear(lats, lons), dtype=np.float64), 5.0, 28.0)
        si_pct = np.clip(np.asarray(self.grs_si.sample_bilinear(lats, lons), dtype=np.float64), 14.0, 28.0)
        cl_pct = np.clip(np.asarray(self.grs_cl.sample_bilinear(lats, lons), dtype=np.float64), 0.1, 1.2)

        # Langlais 2019 evaluates potential in nT-km reference at r = ref_radius + alt (0 km surface / 10 km effective)
        mag_nt = eval_spherical_harmonics_mag(
            lats_deg=lats,
            lons_deg=lons,
            coeffs=self.mag_coeffs,
            ref_radius_km=self.mag_ref_km,
            alt_km=50.0,  # smooth crustal surface-proximal altitude preventing ringing of degree-134 ESD model
            max_degree=110,
            field_scale_nt=1.0,
        )

        # Radiometric Mars temperature & diurnal swing from real TES albedo + thermal inertia + latitude + elev
        cos_l = np.cos(np.deg2rad(np.clip(lats, -89.5, 89.5)))
        mean_temp_c = -126.0 + 78.0 * (cos_l ** 0.70) * (1.0 - 0.35 * (alb - 0.18)) - 0.0022 * elev_m
        # Higher thermal inertia damps diurnal temperature amplitude
        diurnal_amp = np.clip((105.0 - 0.075 * ti) * (0.45 + 0.55 * cos_l), 28.0, 108.0)

        # Physical indices normalized from Odyssey GRS + MOLA + TES
        subsurface_ice = np.clip((h2o_pct - 1.5) / 38.0 + 0.25 * np.clip((np.abs(lats) - 55.0) / 35.0, 0.0, 1.0), 0.04, 0.96)
        basalt = np.clip(0.35 + 0.50 * np.clip((fe_pct / np.maximum(si_pct, 1.0) - 0.45) / 0.45, 0.0, 1.0), 0.25, 0.95)
        anorth = np.clip(0.20 - 0.10 * basalt + 0.06 * np.clip((si_pct - 19.0) / 6.0, 0.0, 1.0), 0.05, 0.28)
        low_basin = np.clip((-1500.0 - elev_m) / 4500.0, 0.0, 1.0)
        clay_salt = np.clip(0.30 + 0.40 * np.clip((cl_pct - 0.2) / 0.7, 0.0, 1.0) + 0.25 * low_basin, 0.15, 0.94)
        rock_abund = np.clip(0.28 + 0.65 * np.clip((ti - 80.0) / 480.0, 0.0, 1.0), 0.20, 0.96)
        roughness = np.clip(0.25 + 0.45 * (slope_deg / 18.0) + 0.25 * rock_abund, 0.15, 0.92)
        solar_frac = np.clip(0.68 - 0.38 * (np.abs(lats) / 90.0) - 0.20 * (alb - 0.15), 0.12, 0.74)
        cold_trap = np.clip(0.60 * subsurface_ice + 0.40 * np.clip((-85.0 - mean_temp_c) / 45.0, 0.0, 1.0), 0.08, 0.98)
        cave_score = np.clip(0.45 * basalt + 0.30 * (slope_deg / 18.0) + 0.15, 0.15, 0.88)
        biosig = np.clip(0.42 * clay_salt + 0.35 * subsurface_ice + 0.20 * rock_abund, 0.15, 0.92)

        low_sun_hrs = np.array(
            [compute_grazing_sun_hours(float(lat), obliquity_deg=25.19) for lat in lats],
            dtype=np.float64,
        )

        out: list[dict[str, float]] = []
        for i in range(len(lats)):
            out.append(
                {
                    "elevation_m": round(float(elev_m[i]), 2),
                    "slope_deg": round(float(slope_deg[i]), 2),
                    "roughness_index": round(float(roughness[i]), 4),
                    "anorthosite_highland_score": round(float(anorth[i]), 4),
                    "basalt_volcanic_score": round(float(basalt[i]), 4),
                    "clay_carbonate_sediment_score": round(float(clay_salt[i]), 4),
                    "regolith_rock_abundance": round(float(rock_abund[i]), 4),
                    "magnetic_anomaly_nt": round(float(mag_nt[i]), 2),
                    "mean_temp_c": round(float(mean_temp_c[i]), 2),
                    "diurnal_amplitude_c": round(float(diurnal_amp[i]), 2),
                    "solar_illumination_frac": round(float(solar_frac[i]), 4),
                    "low_sun_grazing_hours": round(float(low_sun_hrs[i]), 1),
                    "aridity_dryness_index": 0.98,
                    "subsurface_ice_permafrost": round(float(subsurface_ice[i]), 4),
                    "cold_trap_sublimation_index": round(float(cold_trap[i]), 4),
                    "subsurface_cave_drilling_score": round(float(cave_score[i]), 4),
                    "biosignature_preservation_score": round(float(biosig[i]), 4),
                }
            )
        return out
