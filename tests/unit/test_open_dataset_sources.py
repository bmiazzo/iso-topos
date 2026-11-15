"""Unit tests (DR-4 deterministic fixtures) for open-dataset ETL readers and provenance."""

from __future__ import annotations

import io
import json
import struct
import zipfile
from pathlib import Path

import h5py
import numpy as np
import pytest
import tifffile


def test_emag2_sentinel_filtering_and_gap_interpolation_tracks_provenance():
    """Sentinels (99999, -888, -999, NaN) are stripped, |ΔB| is preserved, and gaps flag provenance."""
    from isotopos.etl.sources.grid_sampler import (
        GlobalGrid,
        fill_raster_gaps_with_mask,
        filter_emag2_sentinels,
    )

    raw = np.array(
        [
            [99999.0, -120.0, 240.0, -888.0],
            [99999.0, 99999.0, -999.0, 310.0],
            [50.0, float("nan"), 180.0, -220.0],
            [-60.0, 90.0, 99999.0, 99999.0],
        ],
        dtype=np.float64,
    )
    cleaned = filter_emag2_sentinels(raw)
    assert cleaned[0, 1] == pytest.approx(120.0)
    assert cleaned[2, 3] == pytest.approx(220.0)
    assert np.isnan(cleaned[0, 0])
    assert np.isnan(cleaned[0, 3])
    assert np.isnan(cleaned[1, 2])
    assert np.isnan(cleaned[2, 1])

    filled, gap_mask = fill_raster_gaps_with_mask(cleaned, max_iterations=4)
    assert not np.isnan(filled).any()
    assert bool(gap_mask[0, 1]) is False  # originally measured pixel
    assert bool(gap_mask[1, 1]) is True   # filled track gap

    # Sampling right inside the original gap reports interpolated=True; measured pixel reports False
    grid = GlobalGrid(
        data=filled,
        lat_min=-90.0,
        lat_max=90.0,
        lon_min=-180.0,
        lon_max=180.0,
        interpolated_mask=gap_mask,
    )
    val_meas, interp_meas = grid.sample_nearest_with_provenance(lat=67.5, lon=-45.0)
    val_gap, interp_gap = grid.sample_nearest_with_provenance(lat=22.5, lon=-45.0)
    assert val_meas == pytest.approx(120.0)
    assert interp_meas is False
    assert val_gap > 0.0
    assert interp_gap is True


def test_pds_label_and_binary_raster_reader_supports_msb_and_lsb_0_360(tmp_path: Path):
    """PDS3 .lbl + .img reader decodes scaling, missing constant, endianness, and 0..360 lon."""
    from isotopos.etl.sources.raster_readers import load_pds_raster, parse_pds_label

    lbl = """
    PDS_VERSION_ID = "PDS3"
    LINES = 2
    LINE_SAMPLES = 4
    SAMPLE_TYPE = LSB_INTEGER
    SAMPLE_BITS = 16
    SCALING_FACTOR = 0.001
    OFFSET = 0.0
    MISSING_CONSTANT = -32768
    MAXIMUM_LATITUDE = 60.0 <deg>
    MINIMUM_LATITUDE = -60.0 <deg>
    WESTERNMOST_LONGITUDE = 0.0 <deg>
    EASTERNMOST_LONGITUDE = 360.0 <deg>
    """
    lbl_path = tmp_path / "test_diviner.lbl"
    img_path = tmp_path / "test_diviner.img"
    lbl_path.write_text(lbl, encoding="utf-8")

    # 2x4 int16 little-endian values: 500 -> 0.500, -32768 -> NaN
    vals = [100, 200, -32768, 400, 500, 600, 700, 800]
    img_path.write_bytes(struct.pack("<8h", *vals))

    meta = parse_pds_label(lbl)
    assert meta["LINES"] == 2
    assert meta["LINE_SAMPLES"] == 4
    assert meta["SCALING_FACTOR"] == pytest.approx(0.001)
    assert meta["MISSING_CONSTANT"] == -32768

    grid = load_pds_raster(img_path=img_path, lbl_path=lbl_path)
    assert grid.data.shape == (2, 4)
    assert np.isnan(grid.data[0, 2])
    assert grid.data[1, 3] == pytest.approx(0.8)
    assert grid.lon_0_360 is True
    # Query at negative western longitude (-45 deg -> 315 deg E, column 3 bottom/top)
    sampled = grid.sample_bilinear(lat=-30.0, lon=-45.0)
    assert sampled == pytest.approx(0.8, abs=0.05)


def test_esri_ascii_glim_reader_maps_lithology_scores(tmp_path: Path):
    """GLiM ESRI ASCII reader maps vb->basalt, ev->clay/salt, sc/ss->carbonate, pa->anorthosite."""
    from isotopos.etl.sources.earth_datasets import map_glim_codes_to_scores
    from isotopos.etl.sources.raster_readers import parse_esri_ascii_grid

    asc = "\n".join(
        [
            "ncols         4",
            "nrows         2",
            "xllcorner     -180",
            "yllcorner     -90",
            "cellsize      90",
            "NODATA_value  -9999",
            "2 14 6 -9999",
            "9 3 16 1",
        ]
    )
    grid = parse_esri_ascii_grid(asc)
    assert grid.data.shape == (2, 4)
    assert np.isnan(grid.data[0, 3])

    basalt_scores = map_glim_codes_to_scores(np.array([2, 14, 9, 6], dtype=np.float64))
    assert basalt_scores["basalt_volcanic_score"][0] > 0.85   # vb = code 2
    assert basalt_scores["basalt_volcanic_score"][2] < 0.35   # pa = code 9
    assert basalt_scores["clay_carbonate_sediment_score"][1] > 0.70  # ev = code 14
    assert basalt_scores["clay_carbonate_sediment_score"][3] > 0.70  # sc = code 6
    assert basalt_scores["anorthosite_highland_score"][2] > 0.60     # pa = code 9


def test_spherical_harmonic_mag_evaluation_matches_analytic_axial_dipole():
    """Axial dipole g(1,0) = 100 nT produces |B|=200 nT at poles and 100 nT on equator."""
    from isotopos.etl.sources.raster_readers import eval_spherical_harmonics_mag

    coeffs = [(1, 0, 100.0, 0.0)]
    lats = np.array([90.0, 0.0, -90.0, 30.0])
    lons = np.array([0.0, 120.0, -45.0, 210.0])
    b_mag = eval_spherical_harmonics_mag(
        lats_deg=lats,
        lons_deg=lons,
        coeffs=coeffs,
        ref_radius_km=1737.4,
        alt_km=0.0,
        max_degree=1,
        field_scale_nt=1.0,
    )
    assert b_mag[0] == pytest.approx(200.0, rel=1e-4)
    assert b_mag[1] == pytest.approx(100.0, rel=1e-4)
    assert b_mag[2] == pytest.approx(200.0, rel=1e-4)
    # Away from dipole poles/equator, |B| = g10 * sqrt(1 + 3 sin^2(lat)) -> at 30 deg: sqrt(1 + 0.75)*100
    assert b_mag[3] == pytest.approx(100.0 * np.sqrt(1.75), rel=1e-4)


def test_well_known_baseline_regions_cover_full_hubs_but_preserve_novel_regions():
    """FR-6 baseline classifier masks full Antarctica, Iceland, Hawaii, Atacama, Haughton, Rio Tinto."""
    from isotopos.etl.sources.baseline_regions import is_well_known_baseline_region

    # Baseline hubs (interior, away from original single pin coordinates too!)
    for lat, lon in [
        (-77.86, 160.70),   # McMurdo
        (-82.5, 25.0),      # Deep East Antarctica (>1,000 km from McMurdo!)
        (-71.0, -68.0),     # Antarctic Peninsula
        (64.9, -18.0),      # Central Iceland glacier
        (19.6, -155.5),     # Hawaii Big Island
        (21.4, -158.0),     # Oahu / Hawaiian archipelago
        (-24.08, -69.92),   # Atacama Yungay
        (-22.5, -69.2),     # Northern Chile Atacama corridor
        (75.37, -89.68),    # Devon Island / Haughton
        (37.70, -6.55),     # Rio Tinto
    ]:
        flag, reason = is_well_known_baseline_region(lat, lon)
        assert flag is True and reason, f"Expected ({lat}, {lon}) to be well-known"

    # Novel targets that MUST remain selectable when "Beyond Well-Known Sites" is enabled
    for lat, lon in [
        (37.78, 14.99),     # Etna / Sicily
        (66.52, -52.45),    # Greenland White Mountain
        (38.50, 91.50),     # Qaidam Basin, China
        (-20.13, -67.49),   # Salar de Uyuni, Bolivia
        (-26.60, -67.45),   # Puna de Atacama, Argentina
        (51.70, 36.20),     # Kursk, Russia
        (-21.20, 119.30),   # Pilbara, Australia
    ]:
        flag, _ = is_well_known_baseline_region(lat, lon)
        assert flag is False, f"Novel region ({lat}, {lon}) was wrongly masked as well-known"


def test_independent_h3_vs_hotspot_evaluation_has_no_cave_smearing():
    """H3 macro-cells near a cave hotspot keep regional daylight rather than inheriting 0.0 sunlight."""
    from isotopos.etl.parameter_synthesizer import synthesize_earth_cell_parameters

    # Cell center 0.45 deg from Grotta del Gelo cave on Mt. Etna (37.78, 14.99)
    # With anchor blending removed, surrounding Sicily has healthy regional solar illumination.
    sicily = synthesize_earth_cell_parameters(37.55, 14.55)
    assert sicily["solar_illumination_frac"] > 0.35


def test_country_resolver_assigns_country_and_region_from_geojson(tmp_path: Path):
    """CountryResolver resolves point-in-polygon country and continent names cleanly."""
    from isotopos.etl.sources.baseline_regions import CountryResolver

    mock_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"NAME": "AtacamaTest", "CONTINENT": "South America", "SUBREGION": "South America"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[-71.0, -26.0], [-68.0, -26.0], [-68.0, -22.0], [-71.0, -22.0], [-71.0, -26.0]]],
                },
            }
        ],
    }
    gj_path = tmp_path / "countries.geojson"
    gj_path.write_text(json.dumps(mock_geojson), encoding="utf-8")

    resolver = CountryResolver(gj_path)
    country, region = resolver.resolve(-24.0, -69.5)
    assert country == "AtacamaTest"
    assert region == "South America"
    # Outside polygon & outside coastal buffer
    empty_c, empty_r = resolver.resolve(10.0, 10.0)
    assert empty_c == ""
    assert empty_r == "Africa"


def _make_earth_fixture(tmp_path: Path):
    """Build a lightweight deterministic EarthOpenDatasets instance using synthetic 18x36 grids (DR-4)."""
    from isotopos.etl.sources.baseline_regions import CountryResolver
    from isotopos.etl.sources.earth_datasets import EarthOpenDatasets
    from isotopos.etl.sources.grid_sampler import GlobalGrid

    shape = (18, 36)
    emag_data = np.full(shape, 45.0, dtype=np.float64)
    emag_mask = np.zeros(shape, dtype=bool)
    emag_mask[5, 19] = True  # row=5, col=19 -> exact center (35N, 15E)

    geo = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"NAME": "GreenlandTest", "CONTINENT": "North America", "SUBREGION": "Northern America"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[-60.0, 60.0], [-40.0, 60.0], [-40.0, 72.0], [-60.0, 72.0], [-60.0, 60.0]]],
                },
            }
        ],
    }
    gj = tmp_path / "ne.geojson"
    gj.write_text(json.dumps(geo), encoding="utf-8")

    return EarthOpenDatasets(
        elev_grid=GlobalGrid(data=np.full(shape, 1250.0, dtype=np.float64)),
        slope_grid=GlobalGrid(data=np.full(shape, 6.0, dtype=np.float64)),
        roughness_grid=GlobalGrid(data=np.full(shape, 0.42, dtype=np.float64)),
        emag2_grid=GlobalGrid(data=emag_data, interpolated_mask=emag_mask),
        temp_mean_grid=GlobalGrid(data=np.full(shape, -14.0, dtype=np.float64)),
        diurnal_range_grid=GlobalGrid(data=np.full(shape, 16.0, dtype=np.float64)),
        precip_grid=GlobalGrid(data=np.full(shape, 110.0, dtype=np.float64)),
        solar_clearness_grid=GlobalGrid(data=np.full(shape, 0.72, dtype=np.float64)),
        aridity_grid=GlobalGrid(data=np.full(shape, 0.12, dtype=np.float64)),
        bareness_grid=GlobalGrid(data=np.full(shape, 0.85, dtype=np.float64)),
        glim_grid=GlobalGrid(data=np.full(shape, 9.0, dtype=np.float64)),
        obu_permafrost_grid=GlobalGrid(data=np.full(shape, 0.82, dtype=np.float64)),
        country_resolver=CountryResolver(gj),
    )


def test_earth_open_datasets_extract_batch_produces_17_params_provenance_and_country(tmp_path: Path):
    """EarthOpenDatasets.extract_batch extracts all 17 finite parameters, gap provenance, and country."""
    from isotopos.core.registry import DEFAULT_REGISTRY

    earth_ds = _make_earth_fixture(tmp_path)
    lats = np.array([66.52, 35.0], dtype=np.float64)
    lons = np.array([-52.45, 15.0], dtype=np.float64)

    params_list, interp_list, countries, regions = earth_ds.extract_batch(lats, lons)

    expected_keys = {p.id for p in DEFAULT_REGISTRY.parameters}
    assert len(params_list) == 2
    assert set(params_list[0].keys()) == expected_keys
    assert all(np.isfinite(list(params_list[0].values())))
    assert params_list[0]["low_sun_grazing_hours"] > params_list[1]["low_sun_grazing_hours"]
    assert countries[0] == "GreenlandTest"
    assert regions[0] == "Northern America"
    assert "magnetic_anomaly_nt" not in interp_list[0]
    assert "magnetic_anomaly_nt" in interp_list[1]


def test_moon_and_mars_open_datasets_extract_batch_succeed_with_17_params():
    """MoonOpenDatasets and MarsOpenDatasets extract all 17 finite parameters across latitudes."""
    from isotopos.core.registry import DEFAULT_REGISTRY
    from isotopos.etl.sources.grid_sampler import GlobalGrid
    from isotopos.etl.sources.planetary_datasets import MarsOpenDatasets, MoonOpenDatasets

    shape = (18, 36)
    expected_keys = {p.id for p in DEFAULT_REGISTRY.parameters}

    moon = MoonOpenDatasets(
        elev_grid=GlobalGrid(data=np.full(shape, 1800.0, dtype=np.float64)),
        slope_grid=GlobalGrid(data=np.full(shape, 7.5, dtype=np.float64)),
        rough_grid=GlobalGrid(data=np.full(shape, 12.0, dtype=np.float64)),
        rock_abund_grid=GlobalGrid(data=np.full(shape, 0.04, dtype=np.float64), lat_min=-60.0, lat_max=60.0),
        diviner_st_grid=GlobalGrid(data=np.full(shape, 10.0, dtype=np.float64), lat_min=-60.0, lat_max=60.0),
        lp_grs_grids={
            "feo": GlobalGrid(data=np.full(shape, 5.0, dtype=np.float64)),
            "tio2": GlobalGrid(data=np.full(shape, 1.0, dtype=np.float64)),
            "al2o3": GlobalGrid(data=np.full(shape, 27.0, dtype=np.float64)),
            "neutron": GlobalGrid(data=np.linspace(1.0, 2.0, 18 * 36, dtype=np.float64).reshape(shape)),
        },
        mag_ref_km=1737.4,
        mag_coeffs=[(1, 0, 1e-8, 0.0)],
    )
    mars = MarsOpenDatasets(
        elev_grid=GlobalGrid(data=np.full(shape, -2600.0, dtype=np.float64)),
        slope_grid=GlobalGrid(data=np.full(shape, 2.5, dtype=np.float64)),
        albedo_grid=GlobalGrid(data=np.full(shape, 0.24, dtype=np.float64)),
        ti_night_grid=GlobalGrid(data=np.full(shape, 340.0, dtype=np.float64)),
        grs_h2o=GlobalGrid(data=np.full(shape, 8.5, dtype=np.float64)),
        grs_fe=GlobalGrid(data=np.full(shape, 14.0, dtype=np.float64)),
        grs_si=GlobalGrid(data=np.full(shape, 21.0, dtype=np.float64)),
        grs_cl=GlobalGrid(data=np.full(shape, 0.65, dtype=np.float64)),
        mag_ref_km=3393.5,
        mag_coeffs=[(1, 0, 50.0, 0.0)],
    )

    lats = np.array([0.0, -89.0], dtype=np.float64)
    lons = np.array([25.0, 196.0], dtype=np.float64)

    moon_batch = moon.extract_batch(lats, lons)
    mars_batch = mars.extract_batch(lats, lons)
    assert len(moon_batch) == 2 and len(mars_batch) == 2
    for row in moon_batch:
        assert set(row.keys()) == expected_keys
        assert all(np.isfinite(list(row.values())))
        assert row["clay_carbonate_sediment_score"] == 0.0
        assert row["aridity_dryness_index"] == 1.0
    for row in mars_batch:
        assert set(row.keys()) == expected_keys
        assert all(np.isfinite(list(row.values())))
        assert row["aridity_dryness_index"] == pytest.approx(0.98)
    assert mars_batch[1]["low_sun_grazing_hours"] > mars_batch[0]["low_sun_grazing_hours"]


def test_parse_planetary_grs_tables_and_slope(tmp_path: Path):
    """Odyssey GRS and LP GRS ASCII parsers decode coordinates and fill 9999/-999 sentinels."""
    from isotopos.etl.sources.planetary_datasets import (
        _compute_planet_slope_deg,
        _parse_lp_grs_table,
        _parse_odyssey_grs_table,
    )

    ody_tab = tmp_path / "ody.tab"
    ody_tab.write_text(
        "# header\n"
        "87.5 2.5 12.4 0.5\n"
        "87.5 7.5 9999.999 0.0\n"
        "-87.5 357.5 6.2 0.2\n",
        encoding="utf-8",
    )
    ody_grid = _parse_odyssey_grs_table(ody_tab)
    assert not np.isnan(ody_grid.data).any()
    assert ody_grid.sample_nearest(87.5, 2.5) == pytest.approx(12.4)

    # PDS LP GRS columns 8/11/12 are weight fractions in g/g (0.26 -> 26.0 wt%)
    row_a = ["0", "-2.0", "0.0", "0.0", "2.0", "0", "1.5", "0", "0.26", "0", "0", "0.012", "0.048", "0", "0"]
    row_b = ["1", "0.0", "2.0", "-2.0", "0.0", "0", "-999.0", "0", "0.16", "0", "0", "0.04", "0.175", "0", "0"]
    lp_tab = tmp_path / "lp.tab"
    lp_tab.write_text(" ".join(row_a) + "\n" + " ".join(row_b) + "\n", encoding="utf-8")
    lp_grids = _parse_lp_grs_table(lp_tab)
    assert set(lp_grids.keys()) == {"neutron", "al2o3", "tio2", "feo"}
    assert lp_grids["al2o3"].sample_nearest(-1.0, 1.0) == pytest.approx(26.0)
    assert not np.isnan(lp_grids["neutron"].data).any()

    flat_dem = np.zeros((10, 20), dtype=np.float64)
    assert float(_compute_planet_slope_deg(flat_dem, radius_m=3_396_000.0).max()) == pytest.approx(0.0)
    sloped_dem = np.tile(np.linspace(0.0, 20000.0, 10)[:, None], (1, 20))
    assert float(_compute_planet_slope_deg(sloped_dem, radius_m=3_396_000.0).mean()) > 0.1


def test_enrich_hotspots_from_datasets_preserves_etna_cave_darkness_and_attaches_photos(tmp_path: Path):
    """enrich_hotspots_from_datasets preserves cave solar_illumination_frac=0 while refreshing regional params."""
    from isotopos.etl.catalog_data import EARTH_HOTSPOTS
    from isotopos.etl.sources.hotspot_enrichment import enrich_hotspots_from_datasets

    etna = next(h for h in EARTH_HOTSPOTS if h.id == "grotta_del_gelo_etna")
    greenland = next(h for h in EARTH_HOTSPOTS if h.id == "white_mountain_greenland")
    earth_ds = _make_earth_fixture(tmp_path)

    enriched = enrich_hotspots_from_datasets([etna, greenland], earth_ds=earth_ds)
    enriched_etna, enriched_greenland = enriched

    assert enriched_etna.parameters["solar_illumination_frac"] == 0.0
    assert enriched_etna.parameters["elevation_m"] == pytest.approx(1250.0)
    assert enriched_etna.photo_url is not None and enriched_etna.photo_url.startswith("https://")
    assert enriched_etna.photo_attribution

    assert enriched_greenland.country == "GreenlandTest"
    assert enriched_greenland.is_well_known is False
    assert enriched_greenland.parameters["solar_illumination_frac"] > 0.5
    assert enriched_greenland.photo_url is not None and enriched_greenland.photo_url.startswith("https://")


def test_enrich_hotspots_resolves_countries_and_photos_without_earth_rasters():
    """enrich_hotspots_from_datasets resolves countries from Natural Earth even when earth_ds is None."""
    from isotopos.etl.catalog_data import EARTH_HOTSPOTS
    from isotopos.etl.sources.hotspot_enrichment import enrich_hotspots_from_datasets

    uyuni = next(h for h in EARTH_HOTSPOTS if h.id == "salar_de_uyuni")
    enriched = enrich_hotspots_from_datasets([uyuni], earth_ds=None)
    assert len(enriched) == 1
    assert enriched[0].country == "Bolivia"
    assert enriched[0].photo_url is not None and enriched[0].photo_url.startswith("https://")
    assert enriched[0].photo_attribution


def _encode_tiff_bytes(arr: np.ndarray, *, tiepoint_x: float | None = None, scale_deg: float | None = None) -> bytes:
    """Serialize a 2D array to in-memory GeoTIFF bytes, optionally attaching GeoTIFF tie/scale tags."""
    buf = io.BytesIO()
    extratags: list[tuple[int, int, int, tuple[float, ...], bool]] = []
    if tiepoint_x is not None:
        extratags.append((33922, 12, 6, (0.0, 0.0, 0.0, float(tiepoint_x), 90.0, 0.0), False))
    if scale_deg is not None:
        extratags.append((33550, 12, 3, (float(scale_deg), float(scale_deg), 0.0), False))
    tifffile.imwrite(buf, arr.astype(np.float32, copy=False), extratags=extratags or None)
    return buf.getvalue()


def test_read_tif_safe_masks_nodata_sentinels_and_preserves_valid_values():
    """_read_tif_safe strips NaN/Inf, GDAL |v|>1e15 sentinels, and <-30000 nodata while keeping valid data."""
    from isotopos.etl.sources.earth_datasets import _read_tif_safe

    raw = np.array(
        [
            [-420.5, 0.0, 2845.25],
            [np.nan, np.inf, -np.inf],
            [-3.4e38, 3.4e38, -32768.0],
        ],
        dtype=np.float32,
    )
    decoded = _read_tif_safe(_encode_tiff_bytes(raw))
    assert decoded.dtype == np.float32
    assert decoded[0, 0] == pytest.approx(-420.5)
    assert decoded[0, 1] == pytest.approx(0.0)
    assert decoded[0, 2] == pytest.approx(2845.25)
    assert np.isnan(decoded[1]).all()
    assert np.isnan(decoded[2]).all()


def test_downsample_block_mean_ignores_nans_crops_remainders_and_handles_all_nan_blocks():
    """_downsample_block_mean computes nanmean per (bh, bw) block, crops edge remainders, avoids warnings."""
    from isotopos.etl.sources.earth_datasets import _downsample_block_mean

    arr = np.array(
        [
            [2.0, np.nan, 10.0, 20.0, 99.0],
            [4.0, 6.0, np.nan, np.nan, 99.0],
            [np.nan, np.nan, 1.0, 3.0, 99.0],
            [np.nan, np.nan, 5.0, 7.0, 99.0],
            [88.0, 88.0, 88.0, 88.0, 99.0],
        ],
        dtype=np.float32,
    )
    out = _downsample_block_mean(arr, 2, 2)
    assert out.shape == (2, 2)
    assert out.dtype == np.float32
    assert out[0, 0] == pytest.approx(4.0)
    assert out[0, 1] == pytest.approx(15.0)
    assert np.isnan(out[1, 0])
    assert out[1, 1] == pytest.approx(4.0)


def test_compute_slope_deg_and_relief_flat_ramps_and_antimeridian_wrap():
    """_compute_slope_deg_and_relief returns flat floor, scaled ramps, and continuous wraparound."""
    from isotopos.etl.sources.earth_datasets import _compute_slope_deg_and_relief

    flat = np.full((12, 24), 500.0, dtype=np.float32)
    slope_flat, rough_flat = _compute_slope_deg_and_relief(flat, scale_factor=1.5)
    assert slope_flat.dtype == np.float32
    assert rough_flat.dtype == np.float32
    assert np.allclose(slope_flat, 0.0)
    assert np.allclose(rough_flat, 0.05)

    lat_ramp = np.repeat(np.linspace(0.0, 2000.0, 12, dtype=np.float32)[:, None], 24, axis=1)
    s1, r1 = _compute_slope_deg_and_relief(lat_ramp, scale_factor=1.0)
    s2, _ = _compute_slope_deg_and_relief(lat_ramp, scale_factor=1.85)
    assert float(np.min(s1)) > 0.0
    assert np.allclose(s2, s1 * np.float32(1.85), rtol=1e-5)
    assert float(np.min(r1)) >= 0.05
    assert float(np.max(r1)) <= 0.98

    # Step anomaly on column 0 wraps symmetrically to column -1 via np.roll
    step = np.zeros((12, 24), dtype=np.float32)
    step[:, 0] = 1000.0
    s_wrap, r_wrap = _compute_slope_deg_and_relief(step)
    assert s_wrap[6, -1] == pytest.approx(float(s_wrap[6, 1]), rel=1e-4)
    assert r_wrap[6, -1] > 0.05


def test_obu_permafrost_regridding_rejects_fill_coords_wraps_lon_and_heals_polar_pinholes(tmp_path: Path):
    """_regrid_obu_permafrost_to_equirectangular rejects 1e32 coords, wraps 0..360, heals 1-bin gaps."""
    from isotopos.etl.sources.earth_datasets import _regrid_obu_permafrost_to_equirectangular

    # Build small synthetic HDF5 polar swath with:
    # 1) 1e32 fill coordinates paired with finite PerProb in [0, 1] (must be filtered out)
    # 2) Invalid PerProb (-0.2, 1.4, NaN) on valid coordinates
    # 3) Longitudinal 0..360 wraparound (lon=359.75 -> -0.25)
    # 4) Polar pinhole at (76.25N, -100.25) surrounded by valid bins on 3 sides
    nc_path = tmp_path / "obu_synth.nc"
    lats = np.array(
        [
            [1e32, 1e32, 65.25, 65.25],
            [66.25, 76.25, 76.25, 76.75],
            [75.75, 64.25, np.nan, -150.0],
        ],
        dtype=np.float32,
    )
    lons = np.array(
        [
            [1e32, -10.0, 10.25, 10.25],
            [359.75, -100.75, -99.75, -100.25],
            [-100.25, 10.25, 0.0, 10.0],
        ],
        dtype=np.float32,
    )
    pprob = np.array(
        [
            [0.99, 0.88, -0.2, 1.4],
            [0.72, 0.84, 0.76, 0.80],
            [0.80, np.nan, 0.50, 0.90],
        ],
        dtype=np.float32,
    )
    with h5py.File(nc_path, "w") as hf:
        hf.create_dataset("latitude", data=lats)
        hf.create_dataset("longitude", data=lons)
        hf.create_dataset("PerProb", data=pprob)

    grid = _regrid_obu_permafrost_to_equirectangular(nc_path)
    assert grid.data.shape == (360, 720)
    # North Pole bin (row 0) and out-of-range coordinate row must remain NaN (1e32 rejected)
    assert np.isnan(grid.sample_nearest(89.75, 0.25))
    assert np.isnan(grid.sample_nearest(89.75, -10.0))
    # Invalid PerProb cells stay NaN
    assert np.isnan(grid.sample_nearest(65.25, 10.25))
    assert np.isnan(grid.sample_nearest(64.25, 10.25))
    # 0..360 wrapped longitude maps cleanly to -0.25 deg E
    assert grid.sample_nearest(66.25, -0.25) == pytest.approx(0.72, abs=1e-5)
    # Interior polar spacing pinhole healed locally without filling Southern Hemisphere / equator
    healed = grid.sample_nearest(76.25, -100.25)
    assert np.isfinite(healed)
    assert 0.76 <= healed <= 0.84
    assert np.isnan(grid.sample_nearest(0.0, 0.0))
    assert np.isnan(grid.sample_nearest(-75.0, 20.0))


def test_earth_open_datasets_from_raw_dir_and_interpolation_flags(tmp_path: Path):
    """EarthOpenDatasets.from_raw_dir parses all 8 real-format sources and flags interpolated metrics."""
    from isotopos.etl.sources.earth_datasets import EarthOpenDatasets

    earth_dir = tmp_path / "earth"
    earth_dir.mkdir(parents=True)

    # 1. EMAG2v3 GeoTIFF (0..360 via tiepoint x0=0.0): shape 18x36 -> 3x3 downsample to 6x12
    # Row index in 6x12 is 0..5 -> row 1 is lat +45 deg, col 10 (in 0..360 -> 315 deg = -45 deg E)
    emag_arr = np.full((18, 36), 42.0, dtype=np.float32)
    emag_arr[3:6, 30:33] = 99999.0  # Sentinel block -> interpolated_mask=True in downsampled cell
    (earth_dir / "emag2_v3_upcont.tif").write_bytes(_encode_tiff_bytes(emag_arr, tiepoint_x=0.0))

    # 2. ETOPO2v2c zip: 54x108 int16 little-endian (2:1 global) -> 3x3 downsample to 18x36
    etopo_arr = np.full((54, 108), 1200, dtype="<i2")
    with zipfile.ZipFile(earth_dir / "etopo2v2c_i2_lsb.zip", "w") as zf:
        zf.writestr("ETOPO2v2c_i2_LSB.bin", etopo_arr.tobytes())

    # 3. WorldClim bio & srad zips (6x12 grids): gap at cell corresponding to (lat=+45, lon=-45)
    # In 6x12 grid, row=1 covers [30, 60] (center 45), col=4 covers [-60, -30] (center -45).
    bio1 = np.full((6, 12), 10.0, dtype=np.float32)
    bio2 = np.full((6, 12), 14.0, dtype=np.float32)
    bio12 = np.full((6, 12), 250.0, dtype=np.float32)
    bio1[1, 4] = -3.4e38
    bio2[1, 4] = -3.4e38
    bio12[1, 4] = -3.4e38
    with zipfile.ZipFile(earth_dir / "wc2.1_10m_bio.zip", "w") as zf:
        zf.writestr("wc2.1_10m_bio_1.tif", _encode_tiff_bytes(bio1))
        zf.writestr("wc2.1_10m_bio_2.tif", _encode_tiff_bytes(bio2))
        zf.writestr("wc2.1_10m_bio_12.tif", _encode_tiff_bytes(bio12))

    srad1 = np.full((6, 12), 18000.0, dtype=np.float32)
    srad2 = np.full((6, 12), 20000.0, dtype=np.float32)
    srad1[1, 4] = -3.4e38
    srad2[1, 4] = -3.4e38
    with zipfile.ZipFile(earth_dir / "wc2.1_10m_srad.zip", "w") as zf:
        zf.writestr("wc2.1_10m_srad_01.tif", _encode_tiff_bytes(srad1))
        zf.writestr("wc2.1_10m_srad_02.tif", _encode_tiff_bytes(srad2))

    # 4. Global Aridity 2017 GeoTIFF (18x36 = full -90..90 extent with GeoTIFF tags)
    ar_arr = np.full((18, 36), 0.15, dtype=np.float32)
    ar_arr[4, 13] = 3.4e38
    (earth_dir / "global_aridity_2017.tif").write_bytes(
        _encode_tiff_bytes(ar_arr, tiepoint_x=-180.0, scale_deg=10.0)
    )

    # 5. MODIS landcover zip: stored transposed (lon=24, lat=12) with constant zero dimension-scale
    pft_lon_lat = np.full((24, 12), 11, dtype=np.uint8)
    pft_lon_lat[10, 3] = 2   # Forest patch
    pft_lon_lat[9, 2] = 0    # Water pixel (remains NaN until neighbor fill)
    pft_lon_lat[0, 0] = 127  # Fill pixel
    modis_buf = io.BytesIO()
    with h5py.File(modis_buf, "w") as hf:
        hf.create_dataset("landcover_PFT", data=pft_lon_lat)
        hf.create_dataset("latitude", data=np.zeros(12, dtype=np.float64))
    with zipfile.ZipFile(earth_dir / "modis_landcover.zip", "w") as zf:
        zf.writestr("MODIS_Land_Cover_Climatology.CMG005.nc", modis_buf.getvalue())

    # 6. GLiM 0.5-deg ESRI ASCII zip
    asc_text = "\n".join(
        [
            "ncols 4",
            "nrows 2",
            "xllcorner -180",
            "yllcorner -90",
            "cellsize 90",
            "NODATA_value -9999",
            "2 6 -9999 9",
            "16 2 3 14",
        ]
    )
    with zipfile.ZipFile(earth_dir / "glim_05deg.zip", "w") as zf:
        zf.writestr("glim_05deg.asc", asc_text)

    # 7. Obu permafrost NetCDF/HDF5
    with h5py.File(earth_dir / "obu_permafrost_25km.nc", "w") as hf:
        hf.create_dataset("latitude", data=np.array([[72.25]], dtype=np.float32))
        hf.create_dataset("longitude", data=np.array([[45.25]], dtype=np.float32))
        hf.create_dataset("PerProb", data=np.array([[0.85]], dtype=np.float32))

    # 8. Natural Earth GeoJSON
    gj = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"NAME": "SynthLand", "CONTINENT": "North America", "SUBREGION": "NA"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[-55.0, 40.0], [-40.0, 40.0], [-40.0, 50.0], [-55.0, 50.0], [-55.0, 40.0]]],
                },
            }
        ],
    }
    (tmp_path / "ne_50m_admin_0_countries.geojson").write_text(json.dumps(gj), encoding="utf-8")

    ds = EarthOpenDatasets.from_raw_dir(tmp_path)
    assert ds.emag2_grid.lon_0_360 is True
    assert ds.elev_grid.data.shape == (18, 36)
    assert ds.aridity_grid.lat_min == pytest.approx(-90.0)
    assert ds.bareness_grid.data.shape == (6, 12)
    # Barren=11 dominates bareness grid (0.98) even next to water=0 / fill=127
    assert float(ds.bareness_grid.sample_nearest(70.0, 120.0)) == pytest.approx(0.98, abs=1e-4)

    params, interps, countries, regions = ds.extract_batch(
        lats=np.array([45.0, -45.0], dtype=np.float64),
        lons=np.array([-45.0, 45.0], dtype=np.float64),
    )
    assert len(params) == 2
    assert countries[0] == "SynthLand"
    assert regions[0] == "NA"
    assert set(interps[0]) >= {
        "magnetic_anomaly_nt",
        "mean_temp_c",
        "diurnal_amplitude_c",
        "solar_illumination_frac",
        "aridity_dryness_index",
    }
    assert interps[1] == []


def test_earth_loaders_handle_inverted_modis_latitude_and_subglobal_aridity_extent(tmp_path: Path):
    """MODIS helper flips ascending south-up grids; aridity helper preserves -60..90 coverage."""
    from isotopos.etl.sources.earth_datasets import _load_aridity_grid, _load_modis_bareness_grid

    # Ascending MODIS latitude (-85..+85): south rows are forest (2 -> 0.04), north rows are barren (11 -> 0.98)
    pft = np.full((6, 12), 11, dtype=np.uint8)
    pft[0:2, :] = 2  # bottom 2x2 block = -75..-85 deg S when ascending!
    buf = io.BytesIO()
    with h5py.File(buf, "w") as hf:
        hf.create_dataset("landcover_PFT", data=pft)
        hf.create_dataset("latitude", data=np.linspace(-75.0, 75.0, 6, dtype=np.float64))
    zip_path = tmp_path / "modis_landcover.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("MODIS_CMG005.nc", buf.getvalue())

    bare_grid = _load_modis_bareness_grid(zip_path)
    # After flipping to north-up (origin_top=True), northern latitude (+75) is barren (0.98) and southern (-75) is forest (0.04)
    assert bare_grid.sample_nearest(75.0, 0.0) == pytest.approx(0.98, abs=1e-4)
    assert bare_grid.sample_nearest(-75.0, 0.0) == pytest.approx(0.04, abs=1e-4)

    # Sub-global Aridity GeoTIFF covering -60..90 (150 deg / 360 deg = 15 rows x 36 cols, scale=10 deg)
    ar_sub = np.full((15, 36), 0.33, dtype=np.float32)
    ar_path = tmp_path / "global_aridity_2017.tif"
    ar_path.write_bytes(_encode_tiff_bytes(ar_sub, tiepoint_x=-180.0, scale_deg=10.0))
    ar_grid = _load_aridity_grid(ar_path)
    assert ar_grid.lat_min == pytest.approx(-60.0)
    assert ar_grid.lat_max == pytest.approx(90.0)


def test_earth_loaders_validate_inputs_and_fallback_paths(tmp_path: Path):
    """Error guards and untagged aspect-ratio / pinhole short-circuit paths behave cleanly."""
    from isotopos.etl.sources.earth_datasets import (
        _heal_local_grid_pinholes,
        _load_aridity_grid,
        _load_etopo_grids,
        _load_worldclim_srad_grid,
        _read_h5_array,
    )

    h5_path = tmp_path / "group_only.h5"
    with h5py.File(h5_path, "w") as hf:
        hf.create_group("nested_group")
    with h5py.File(h5_path, "r") as hf:
        with pytest.raises(TypeError, match="HDF5 Dataset"):
            _read_h5_array(hf, "nested_group")

    bad_etopo = tmp_path / "bad_etopo.zip"
    with zipfile.ZipFile(bad_etopo, "w") as zf:
        zf.writestr("bad.bin", b"\x00\x01\x02\x03")
    with pytest.raises(ValueError, match="2:1 equirectangular"):
        _load_etopo_grids(bad_etopo)

    empty_srad = tmp_path / "empty_srad.zip"
    with zipfile.ZipFile(empty_srad, "w") as zf:
        zf.writestr("readme.txt", "no tiffs")
    with pytest.raises(ValueError, match="No .tif monthly bands"):
        _load_worldclim_srad_grid(empty_srad)

    untagged_sub = tmp_path / "aridity_untagged.tif"
    untagged_sub.write_bytes(_encode_tiff_bytes(np.full((15, 36), 0.25, dtype=np.float32)))
    assert _load_aridity_grid(untagged_sub).lat_min == pytest.approx(-60.0)

    complete = np.ones((4, 4), dtype=np.float64)
    assert np.array_equal(_heal_local_grid_pinholes(complete), complete)


def test_moon_and_mars_open_datasets_from_raw_dir_and_raster_edges(tmp_path: Path):
    """DR-4: Deterministic synthetic PDS3/GRS/SH fixtures exercise MoonOpenDatasets and MarsOpenDatasets end-to-end."""
    import gzip
    from isotopos.etl.sources.planetary_datasets import MarsOpenDatasets, MoonOpenDatasets
    from isotopos.etl.sources.raster_readers import (
        eval_spherical_harmonics_mag,
        load_pds_raster,
        parse_esri_ascii_grid,
        parse_spherical_harmonic_table,
    )

    def _write_pds_i16(
        directory: Path,
        stem: str,
        arr_i16: np.ndarray,
        scale: float = 1.0,
        offset: float = 0.0,
        lat_min: float = -90.0,
        lat_max: float = 90.0,
        lon_min: float = 0.0,
        lon_max: float = 360.0,
    ) -> None:
        nrows, ncols = arr_i16.shape
        (directory / f"{stem}.img").write_bytes(np.asarray(arr_i16, dtype="<i2").tobytes())
        (directory / f"{stem}.lbl").write_text(
            "\n".join(
                [
                    f"LINES = {nrows}",
                    f"LINE_SAMPLES = {ncols}",
                    "SAMPLE_TYPE = LSB_INTEGER",
                    "SAMPLE_BITS = 16",
                    f"SCALING_FACTOR = {scale}",
                    f"OFFSET = {offset}",
                    f"MINIMUM_LATITUDE = {lat_min} <deg>",
                    f"MAXIMUM_LATITUDE = {lat_max} <deg>",
                    f"WESTERNMOST_LONGITUDE = {lon_min} <deg>",
                    f"EASTERNMOST_LONGITUDE = {lon_max} <deg>",
                    "CENTER_LONGITUDE = 180.0 <deg>",
                ]
            ),
            encoding="utf-8",
        )

    moon_dir = tmp_path / "moon"
    moon_dir.mkdir()
    _write_pds_i16(moon_dir, "ldem_4", np.full((6, 12), 1500, dtype="<i2"), scale=1.0)
    _write_pds_i16(moon_dir, "ldsm_16", np.full((8, 16), 80, dtype="<i2"), scale=0.1)
    _write_pds_i16(moon_dir, "ldrm_16", np.full((8, 16), 40, dtype="<i2"), scale=0.1)
    _write_pds_i16(
        moon_dir,
        "dgdr_ra_avg_cyl_032_img",
        np.full((6, 12), 50, dtype="<i2"),
        scale=0.01,
        lat_min=-60.0,
        lat_max=60.0,
    )
    _write_pds_i16(
        moon_dir,
        "dgdr_st_avg_cyl_032_img",
        np.full((6, 12), 180, dtype="<i2"),
        scale=1.0,
        lat_min=-60.0,
        lat_max=60.0,
    )
    # Minimal Lunar Prospector GRS table (>=15 columns; 0:rec, 1..4:lat/lon bounds, 6:neutron, 8:al2o3, 11:tio2, 12:feo)
    (moon_dir / "lpgrs_high1_elem_abundance_2deg.tab").write_text(
        "1 -90.0 90.0 -180.0 180.0 0 0.5 0 0.25 0 0 0.02 0.06 0 0\n",
        encoding="utf-8",
    )
    with gzip.open(moon_dir / "T2015_449.sh.gz", "wt", encoding="utf-8") as gz:
        gz.write("1737.4 2\n")
        gz.write("1 0 12.0 0.0\n")
        gz.write("2 1 8.0 -4.0\n")

    moon = MoonOpenDatasets.from_raw_dir(tmp_path)
    moon_batch = moon.extract_batch(np.array([-89.0, 0.0]), np.array([0.0, 45.0]))
    assert len(moon_batch) == 2
    assert moon_batch[0]["elevation_m"] == pytest.approx(1500.0)
    assert moon_batch[0]["biosignature_preservation_score"] == 0.0

    mars_dir = tmp_path / "mars"
    mars_dir.mkdir()
    _write_pds_i16(mars_dir, "megt90n000cb", np.full((6, 12), -2000, dtype="<i2"), scale=1.0)
    _write_pds_i16(mars_dir, "global_albedo_8ppd", np.full((6, 12), 25, dtype="<i2"), scale=0.01)
    _write_pds_i16(mars_dir, "global_ti_night_2007", np.full((6, 12), 300, dtype="<i2"), scale=1.0)
    for tbl, val in [("h2o_sr_5x5.tab", 8.5), ("fe_sr_5x5.tab", 14.0), ("si_sr_5x5.tab", 21.0), ("cl_sr_5x5.tab", 0.4)]:
        (mars_dir / tbl).write_text(f"-90.0 180.0 {val}\n90.0 180.0 {val}\n", encoding="utf-8")
    with gzip.open(mars_dir / "Langlais2019.sh.gz", "wt", encoding="utf-8") as gz:
        gz.write("3393.5 2\n")
        gz.write("1 0 15.0 0.0\n")
        gz.write("2 2 6.0 3.0\n")

    mars = MarsOpenDatasets.from_raw_dir(tmp_path)
    mars_batch = mars.extract_batch(np.array([-45.0, 18.0]), np.array([180.0, 77.0]))
    assert len(mars_batch) == 2
    assert mars_batch[0]["elevation_m"] == pytest.approx(-2000.0)
    assert mars_batch[0]["magnetic_anomaly_nt"] > 0.0

    # Extra raster_readers edges: ESRI ASCII NODATA & unknown PDS sample type
    asc_text = "ncols 2\nnrows 2\nxllcorner -180\nyllcorner -90\ncellsize 90\nnodata_value -9999\n1 -9999\n3 4\n"
    asc = parse_esri_ascii_grid(asc_text)
    assert np.isnan(asc.data[0, 1]) and asc.data[1, 1] == 4.0

    ref, lmax, coeffs = parse_spherical_harmonic_table(mars_dir / "Langlais2019.sh.gz", max_degree=2)
    mag = eval_spherical_harmonics_mag(np.array([0.0]), np.array([90.0]), coeffs, ref_radius_km=ref, max_degree=lmax)
    assert mag[0] > 0.0

    bad_lbl = tmp_path / "bad.lbl"
    bad_img = tmp_path / "bad.img"
    bad_img.write_bytes(b"\x00\x00\x00\x00")
    bad_lbl.write_text("LINES = 2\nLINE_SAMPLES = 2\nSAMPLE_TYPE = WEIRD_TYPE\nSAMPLE_BITS = 8\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported PDS"):
        load_pds_raster(bad_img, bad_lbl)


def test_as_tiff_page_resolves_page_and_frame(tmp_path: Path):
    """_as_tiff_page resolves both TiffPage and TiffFrame objects so .tags is always valid."""
    from isotopos.etl.sources.earth_datasets import _as_tiff_page

    tif_path = tmp_path / "uniform_stack.tif"
    tifffile.imwrite(tif_path, np.ones((2, 4, 4), dtype=np.float32), photometric="minisblack")
    with tifffile.TiffFile(tif_path) as tf:
        tf.pages.useframes = True
        page0 = _as_tiff_page(tf.pages[0])
        assert isinstance(page0, tifffile.TiffPage)
        assert page0.tags.get("ImageWidth") is not None

        page1 = tf.pages[1]
        assert isinstance(page1, tifffile.TiffFrame)
        resolved1 = _as_tiff_page(page1)
        assert isinstance(resolved1, tifffile.TiffPage)
        assert resolved1.tags.get("ImageWidth") is not None


