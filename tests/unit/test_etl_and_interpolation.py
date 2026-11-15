"""Failing-first unit tests for offline ETL, grazing sun physics, H3 grid, and Moon/Mars interpolation."""

import pytest

from isotopos.core.models import PlanetaryBody
from isotopos.core.registry import DEFAULT_REGISTRY
from isotopos.etl.catalog_data import EARTH_HOTSPOTS, PLANETARY_PRESETS
from isotopos.etl.interpolator import PlanetaryGridInterpolator
from isotopos.etl.spatial_builder import (
    _load_land_h3_cells,
    _safe_hex_geometry,
    build_earth_h3_grid,
    build_planetary_grid,
    compute_grazing_sun_hours,
)
from isotopos.scoring.engine import AnalogScoringEngine


def test_grazing_sun_hours_increases_at_polar_latitudes():
    """parameters.md: Grazing sun hours increase monotonically from equator to Arctic Circle to High Arctic."""
    equator = compute_grazing_sun_hours(0.0)
    greenland = compute_grazing_sun_hours(66.5)
    high_arctic = compute_grazing_sun_hours(78.0)
    assert equator < 400.0
    assert greenland > 1100.0
    assert high_arctic > greenland


def test_grazing_sun_hours_handles_moon_mars_and_earth_obliquities():
    """compute_grazing_sun_hours computes valid bounded polar/equatorial hours across Earth, Moon, and Mars."""
    earth_polar = compute_grazing_sun_hours(-78.0, obliquity_deg=23.44)
    mars_polar = compute_grazing_sun_hours(-80.0, obliquity_deg=25.19)
    mars_eq = compute_grazing_sun_hours(0.0, obliquity_deg=25.19)
    moon_polar = compute_grazing_sun_hours(-89.0, obliquity_deg=1.54)
    moon_eq = compute_grazing_sun_hours(0.0, obliquity_deg=1.54)

    assert 0.0 <= earth_polar <= 2400.0
    assert mars_polar > mars_eq > 0.0
    assert moon_polar > moon_eq > 0.0
    assert compute_grazing_sun_hours(-66.5, obliquity_deg=23.44) == compute_grazing_sun_hours(66.5, obliquity_deg=23.44)



def test_catalogs_have_12_presets_and_26_hotspots_all_valid():
    """FR-2, FR-5, FR-6 & parameters.md: 12 Moon/Mars presets + 26 Baseline/Novel Earth hotspots."""
    assert len(PLANETARY_PRESETS) == 12
    assert len(EARTH_HOTSPOTS) == 26

    param_ids = {p.id for p in DEFAULT_REGISTRY.parameters}
    for preset in PLANETARY_PRESETS:
        assert set(preset.parameters.keys()) == param_ids

    well_known = [h for h in EARTH_HOTSPOTS if h.is_well_known]
    novel = [h for h in EARTH_HOTSPOTS if not h.is_well_known]
    assert len(well_known) == 6
    assert len(novel) == 20
    for hotspot in EARTH_HOTSPOTS:
        assert set(hotspot.parameters.keys()) == param_ids


def test_planetary_grid_interpolator_handles_coordinates_and_extrapolation_flags():
    """FR-3: Preset extraction has is_extrapolated=False; arbitrary (lat, lon) has is_extrapolated=True."""
    moon_grid = build_planetary_grid(PlanetaryBody.MOON, step_deg=10.0)
    mars_grid = build_planetary_grid(PlanetaryBody.MARS, step_deg=10.0)

    interpolator = PlanetaryGridInterpolator(
        registry=DEFAULT_REGISTRY,
        presets=PLANETARY_PRESETS,
        moon_grid=moon_grid,
        mars_grid=mars_grid,
    )

    preset_target = interpolator.extract_preset("shackleton_rim")
    assert preset_target.is_extrapolated is False
    assert preset_target.extrapolated_parameters == []

    # Arbitrary coordinate on Moon (both negative and >180 lon supported)
    arb_moon = interpolator.extract_coordinate(PlanetaryBody.MOON, lat=-82.3, lon=215.7)
    assert arb_moon.is_extrapolated is True
    assert len(arb_moon.extrapolated_parameters) == len(DEFAULT_REGISTRY.parameters)

    arb_mars = interpolator.extract_coordinate(PlanetaryBody.MARS, lat=12.4, lon=-45.2)
    assert arb_mars.is_extrapolated is True
    assert arb_mars.body == PlanetaryBody.MARS


def test_adaptive_h3_earth_grid_builds_valid_geojson_and_parameters():
    """FR-4 & DR-2: Uniform H3 Res 4 grid builds valid land cells with no antimeridian spikes."""
    import h3

    sites, geojson = build_earth_h3_grid(max_cells=600)
    assert len(sites) >= 200
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == len(sites)

    param_ids = {p.id for p in DEFAULT_REGISTRY.parameters}
    for site in sites[:25]:
        assert h3.get_resolution(site.id) == 4
        assert set(site.parameters.keys()) == param_ids

    for feat in geojson["features"]:
        geom = feat["geometry"]
        assert geom["type"] in ("Polygon", "MultiPolygon")
        rings = [geom["coordinates"][0]] if geom["type"] == "Polygon" else [p[0] for p in geom["coordinates"]]
        for ring in rings:
            lons = [pt[0] for pt in ring]
            lats = [pt[1] for pt in ring]
            assert max(lons) - min(lons) <= 90.0
            for a, b in zip(ring[:-1], ring[1:]):
                assert abs(a[0] - b[0]) <= 90.0
            assert min(lats) >= -90.0 and max(lats) <= 90.0


def test_antimeridian_hex_geometry_splits_cleanly_into_multipolygon():
    """FR-4 & DEC-005: Antimeridian H3 cells split into valid MultiPolygon halves instead of being dropped."""
    import h3

    antimeridian_cid = h3.latlng_to_cell(66.5, 179.95, 4)
    geom = _safe_hex_geometry(antimeridian_cid)
    assert geom is not None
    assert geom["type"] == "MultiPolygon"
    assert len(geom["coordinates"]) == 2
    for poly in geom["coordinates"]:
        ring = poly[0]
        lons = [pt[0] for pt in ring]
        lats = [pt[1] for pt in ring]
        assert max(lons) - min(lons) <= 10.0
        assert min(lons) >= -180.0 and max(lons) <= 180.0
        assert min(lats) >= -90.0 and max(lats) <= 90.0


def test_south_pole_hex_geometry_is_preserved_without_mercator_clamping():
    """DEC-014 / DEC-015: Polar H3 cells down to -90 deg fan into <=90°-span wedges for CesiumJS 3D/2D."""
    import h3

    for lat, lon in [(-90.0, 0.0), (-86.5, 45.0), (-89.2, 179.9)]:
        cid = h3.latlng_to_cell(lat, lon, 4)
        geom = _safe_hex_geometry(cid)
        assert geom is not None, f"Polar cell at ({lat}, {lon}) was dropped"
        assert geom["type"] in ("Polygon", "MultiPolygon")
        rings = [geom["coordinates"][0]] if geom["type"] == "Polygon" else [p[0] for p in geom["coordinates"]]
        all_lats = [pt[1] for ring in rings for pt in ring]
        assert min(all_lats) < -85.0
        for ring in rings:
            lons = [pt[0] for pt in ring]
            assert max(lons) - min(lons) <= 90.0
            for a, b in zip(ring[:-1], ring[1:]):
                assert abs(a[0] - b[0]) <= 90.0

    # Specifically verify the South Pole-encircling cell fans into a MultiPolygon reaching -90.0
    sp_cid = h3.latlng_to_cell(-90.0, 0.0, 4)
    sp_geom = _safe_hex_geometry(sp_cid)
    assert sp_geom is not None and sp_geom["type"] == "MultiPolygon"
    assert len(sp_geom["coordinates"]) >= 6
    sp_lats = [pt[1] for poly in sp_geom["coordinates"] for pt in poly[0]]
    assert min(sp_lats) == pytest.approx(-90.0)


def test_fan_polar_ring_handles_north_and_south_poles():
    """fan_polar_ring splits polar-encircling rings around +/-90° into <=90° lon wedges."""
    from isotopos.etl.h3_geometry import fan_polar_ring

    lons = [143.021, 90.5229, 35.8098, -31.4889, -103.228, -162.7501]
    south_lats = [-89.7199, -89.7226, -89.7593, -89.7989, -89.7803, -89.7406]
    south_geom = fan_polar_ring(lons, south_lats)
    assert south_geom is not None and south_geom["type"] == "MultiPolygon"
    for poly in south_geom["coordinates"]:
        ring = poly[0]
        assert max(p[0] for p in ring) - min(p[0] for p in ring) <= 90.0
        assert any(p[1] == -90.0 for p in ring)

    north_lats = [abs(lt) for lt in south_lats]
    north_geom = fan_polar_ring(list(reversed(lons)), north_lats)
    assert north_geom is not None and north_geom["type"] == "MultiPolygon"
    for poly in north_geom["coordinates"]:
        ring = poly[0]
        assert max(p[0] for p in ring) - min(p[0] for p in ring) <= 90.0
        assert any(p[1] == 90.0 for p in ring)


def test_natural_earth_coastline_mask_excludes_oceans_and_includes_islands():
    """FR-4 & DEC-005/DEC-014/DEC-015: Land + Antarctic ice shelves cover poles & vertices, excluding oceans."""
    import h3

    cells = _load_land_h3_cells(res=4)
    assert len(cells) > 70000

    # All 26 curated hotspots must be covered
    for hs in EARTH_HOTSPOTS:
        assert h3.latlng_to_cell(hs.lat, hs.lon, 4) in cells, f"Missing hotspot {hs.id}"

    # Key islands, peninsulas, polar sites, Antarctic ice shelves, Arctic vertices, and antimeridian regions
    expected_land = [
        (19.82, -155.47),   # Hawaii
        (65.03, -16.75),    # Iceland
        (78.90, 16.00),     # Svalbard
        (28.27, -16.64),    # Canary Islands
        (66.50, 179.50),    # Chukotka East
        (66.50, -179.50),   # Chukotka West
        (-43.50, 170.50),   # New Zealand
        (-77.50, 162.50),   # McMurdo Dry Valleys (Antarctica)
        (-80.37, 77.35),    # Dome A (East Antarctica)
        (-86.50, 45.00),    # East Antarctic Polar Plateau (< -84.5)
        (-89.90, 0.00),     # South Pole
        (-81.50, -175.00),  # Ross Ice Shelf (Antarctica)
        (-80.50, -55.00),   # Filchner-Ronne Ice Shelf (Antarctica)
        (-70.50, 71.00),    # Amery Ice Shelf (Antarctica)
        (62.8189, -91.3495),  # Hudson Bay NE vertex (840ea69ffffffff)
    ]
    for lat, lon in expected_land:
        assert h3.latlng_to_cell(lat, lon, 4) in cells, f"Missing land ({lat}, {lon})"

    # Open oceans & seas that were erroneously tiled by the old box mask must be False
    expected_ocean = [
        (40.0, -35.0),      # Mid-North Atlantic
        (36.0, 18.0),       # Central Mediterranean Sea
        (20.0, 38.5),       # Red Sea
        (-30.0, -130.0),    # South Pacific
        (-20.0, 80.0),      # Indian Ocean
        (-60.0, 0.0),       # Southern Ocean
        (-75.0, -175.0),    # Ross Sea open water
    ]
    for lat, lon in expected_ocean:
        assert h3.latlng_to_cell(lat, lon, 4) not in cells, f"Ocean tiled at ({lat}, {lon})"


def test_scientific_sanity_lunar_south_pole_and_mars_astrobiology_rankings():
    """parameters.md sanity check: White Mountain/Haughton rank high for Moon; Lake Salda/Pilbara for Jezero."""
    engine = AnalogScoringEngine(DEFAULT_REGISTRY)

    shackleton = next(p for p in PLANETARY_PRESETS if p.id == "shackleton_rim")
    lunar_res = engine.evaluate(
        sites=EARTH_HOTSPOTS,
        target=shackleton,
        weights=shackleton.recommended_weights,
        top_k=5,
    )
    top_lunar_ids = {r.site.id for r in lunar_res.ranked_results}
    assert "white_mountain_greenland" in top_lunar_ids or "haughton_crater" in top_lunar_ids

    jezero = next(p for p in PLANETARY_PRESETS if p.id == "jezero_crater")
    mars_res = engine.evaluate(
        sites=EARTH_HOTSPOTS,
        target=jezero,
        weights=jezero.recommended_weights,
        top_k=5,
    )
    top_mars_ids = {r.site.id for r in mars_res.ranked_results}
    assert "lake_salda" in top_mars_ids or "pilbara_shark_bay" in top_mars_ids


def test_earth_parameter_synthesis_has_no_rectangular_discontinuities():
    """Earth grid synthesis must vary smoothly across former lat/lon box boundaries (no rectangular clusters)."""
    from isotopos.etl.spatial_builder import _synthesize_earth_cell_parameters

    boundary_pairs = [
        ((15.9, 10.0), (16.1, 10.0)),      # Former Sahara/arid belt edge
        ((66.0, -42.1), (66.0, -41.9)),    # Former West Greenland anorthosite box
        ((23.9, 76.0), (24.1, 76.0)),      # Former Deccan basalt box
        ((26.9, 88.0), (27.1, 88.0)),      # Former Tibetan Plateau box
        ((64.9, 90.0), (65.1, 90.0)),      # Former polar cutoff
        ((53.9, 105.0), (54.1, 105.0)),    # Former permafrost cutoff
    ]
    for (lat1, lon1), (lat2, lon2) in boundary_pairs:
        p1 = _synthesize_earth_cell_parameters(lat1, lon1)
        p2 = _synthesize_earth_cell_parameters(lat2, lon2)
        assert abs(p2["elevation_m"] - p1["elevation_m"]) < 400.0
        assert abs(p2["mean_temp_c"] - p1["mean_temp_c"]) < 3.5
        assert abs(p2["diurnal_amplitude_c"] - p1["diurnal_amplitude_c"]) < 3.0
        assert abs(p2["aridity_dryness_index"] - p1["aridity_dryness_index"]) < 0.12
        assert abs(p2["anorthosite_highland_score"] - p1["anorthosite_highland_score"]) < 0.12
        assert abs(p2["basalt_volcanic_score"] - p1["basalt_volcanic_score"]) < 0.12
        assert abs(p2["clay_carbonate_sediment_score"] - p1["clay_carbonate_sediment_score"]) < 0.12
        assert abs(p2["biosignature_preservation_score"] - p1["biosignature_preservation_score"]) < 0.12


def test_planetary_parameter_synthesis_has_no_rectangular_discontinuities():
    """Moon and Mars parameter fields must transition smoothly without sharp lat/lon box edges."""
    from isotopos.etl.spatial_builder import _synthesize_planetary_point

    moon_edge = (_synthesize_planetary_point(PlanetaryBody.MOON, 44.5, 20.0),
                 _synthesize_planetary_point(PlanetaryBody.MOON, 45.5, 20.0))
    assert abs(moon_edge[1]["anorthosite_highland_score"] - moon_edge[0]["anorthosite_highland_score"]) < 0.15
    assert abs(moon_edge[1]["basalt_volcanic_score"] - moon_edge[0]["basalt_volcanic_score"]) < 0.15
    assert abs(moon_edge[1]["elevation_m"] - moon_edge[0]["elevation_m"]) < 600.0

    mars_edge = (_synthesize_planetary_point(PlanetaryBody.MARS, 24.5, 245.0),
                 _synthesize_planetary_point(PlanetaryBody.MARS, 25.5, 245.0))
    assert abs(mars_edge[1]["elevation_m"] - mars_edge[0]["elevation_m"]) < 1200.0
    assert abs(mars_edge[1]["clay_carbonate_sediment_score"] - mars_edge[0]["clay_carbonate_sediment_score"]) < 0.15


def test_h3_grid_marks_well_known_baseline_vicinity():
    """FR-6: Baseline coordinates in Atacama, Antarctica, Iceland, Hawaii are flagged while Greenland stays novel."""
    import h3
    from isotopos.etl.spatial_builder import (
        _is_near_well_known_baseline,
        _synthesize_earth_cell_parameters,
    )

    for lat, lon in [(-24.08, -69.92), (-82.0, 20.0), (64.9, -18.0), (19.6, -155.5)]:
        cid = h3.latlng_to_cell(lat, lon, 4)
        c_lat, c_lon = h3.cell_to_latlng(cid)
        assert _is_near_well_known_baseline(c_lat, c_lon) is True
        assert _synthesize_earth_cell_parameters(c_lat, c_lon)["aridity_dryness_index"] >= 0.0

    # Greenland White Mountain is explicitly novel (is_well_known=False)
    greenland_cid = h3.latlng_to_cell(66.52, -52.45, 4)
    g_lat, g_lon = h3.cell_to_latlng(greenland_cid)
    assert _is_near_well_known_baseline(g_lat, g_lon) is False


def test_independent_planetary_and_earth_extraction_has_no_anchor_smearing():
    """Planetary and Earth evaluation are independent at neighboring coordinates (no 4.5°/16° anchor blending)."""
    from isotopos.etl.spatial_builder import _synthesize_earth_cell_parameters, _synthesize_planetary_point

    # Etna hotspot has solar_illumination_frac=0.0 (cave); a neighbor 0.45° away keeps normal daylight
    etna_neighbor = _synthesize_earth_cell_parameters(37.55, 14.55)
    assert etna_neighbor["solar_illumination_frac"] > 0.35

    # Planetary extraction uses the gridded field without teleporting distant preset anomalies across 16°
    moon_polar = _synthesize_planetary_point(PlanetaryBody.MOON, -89.5, 0.0)
    moon_off_pole = _synthesize_planetary_point(PlanetaryBody.MOON, -75.0, 0.0)
    assert moon_polar["low_sun_grazing_hours"] > moon_off_pole["low_sun_grazing_hours"]


def test_load_land_h3_cells_returns_defensive_copy():
    """Mutating the set returned by _load_land_h3_cells must not corrupt the cached land mask."""
    cells_a = _load_land_h3_cells(res=4)
    initial_len = len(cells_a)
    cells_a.add("fake_cell_id")
    cells_b = _load_land_h3_cells(res=4)
    assert len(cells_b) == initial_len
    assert "fake_cell_id" not in cells_b


def test_h3_geometry_antimeridian_clipping_and_ring_closure():
    """clip_antimeridian_halfplane splits antimeridian-spanning polygons without crossing the globe."""
    from isotopos.etl.h3_geometry import clip_antimeridian_halfplane, close_rounded_ring, safe_hex_geometry
    import h3

    # Unwrapped 0..360 polygon crossing 180° (178 -> 182)
    pts_360 = [(178.0, 10.0), (182.0, 10.0), (182.0, 12.0), (178.0, 12.0)]
    east_180 = clip_antimeridian_halfplane(pts_360, keep_le_180=True)
    west_360 = clip_antimeridian_halfplane(pts_360, keep_le_180=False)
    assert len(east_180) >= 4 and len(west_360) >= 4
    assert all(0.0 <= pt[0] <= 180.0 for pt in east_180)
    assert all(180.0 <= pt[0] <= 360.0 for pt in west_360)

    ring = close_rounded_ring([(1.234567, 2.345678), (3.0, 4.0), (5.0, 6.0)])
    assert ring is not None and ring[0] == ring[-1]
    assert close_rounded_ring([(1.0, 2.0)]) is None

    cid = h3.latlng_to_cell(0.0, 179.99, 2)
    geom = safe_hex_geometry(cid)
    assert geom is not None
    assert geom["type"] in ("Polygon", "MultiPolygon")


def test_blend_with_anchors_is_symmetric_and_order_independent():
    """blend_with_anchors produces identical values regardless of anchor list ordering."""
    from isotopos.etl.geodesic_math import blend_with_anchors

    base = {"elevation_m": 500.0, "slope_deg": 5.0}
    anchors = [
        (-85.0, 10.0, {"elevation_m": 2000.0, "slope_deg": 20.0}),
        (-86.0, 15.0, {"elevation_m": 4000.0, "slope_deg": 10.0}),
    ]
    res_forward = blend_with_anchors(-85.4, 12.0, dict(base), anchors, max_dist_deg=8.0, sigma_deg=2.5)
    res_reverse = blend_with_anchors(-85.4, 12.0, dict(base), list(reversed(anchors)), max_dist_deg=8.0, sigma_deg=2.5)
    assert res_forward["elevation_m"] == pytest.approx(res_reverse["elevation_m"], abs=1e-12)
    assert res_forward["slope_deg"] == pytest.approx(res_reverse["slope_deg"], abs=1e-12)

    # Distant coordinates outside max_dist_deg stay unchanged; exact anchor locks closely
    far = blend_with_anchors(10.0, 10.0, dict(base), anchors, max_dist_deg=4.0, sigma_deg=1.5)
    assert far == base
    at_first = blend_with_anchors(-85.0, 10.0, dict(base), anchors, max_dist_deg=8.0, sigma_deg=2.5)
    assert at_first["elevation_m"] == pytest.approx(2000.0, abs=200.0)




