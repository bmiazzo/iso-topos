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
            assert min(lats) >= -85.0 and max(lats) <= 85.0


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
        assert min(lats) >= -84.95 and max(lats) <= 84.95


def test_natural_earth_coastline_mask_excludes_oceans_and_includes_islands():
    """FR-4 & DEC-005: Natural Earth 50m mask excludes open oceans and includes continents, islands, and hotspots."""
    import h3

    cells = _load_land_h3_cells(res=4)
    assert len(cells) > 70000

    # All 26 curated hotspots must be covered
    for hs in EARTH_HOTSPOTS:
        if abs(hs.lat) <= 84.5:
            assert h3.latlng_to_cell(hs.lat, hs.lon, 4) in cells, f"Missing hotspot {hs.id}"

    # Key islands, peninsulas, polar sites, and antimeridian regions must be present
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
    """FR-6: H3 cells overlapping well-known baseline regions are flagged is_well_known=True."""
    import h3

    sites, _ = build_earth_h3_grid(max_cells=None, res=4)
    by_id = {s.id: s for s in sites}
    atacama_cid = h3.latlng_to_cell(-24.08, -69.92, 4)
    assert by_id[atacama_cid].is_well_known is True
    # Greenland White Mountain is explicitly novel (is_well_known=False)
    greenland_cid = h3.latlng_to_cell(66.52, -52.45, 4)
    assert by_id[greenland_cid].is_well_known is False


def test_planetary_and_earth_anchor_blending_is_order_independent_and_preserves_shackleton():
    """Shackleton Rim (-89.9, 0.0) must not be overwritten by nearby Malapert Massif (-86.0, 0.0)."""
    from isotopos.etl.spatial_builder import _synthesize_earth_cell_parameters, _synthesize_planetary_point

    shackleton = next(p for p in PLANETARY_PRESETS if p.id == "shackleton_rim")
    synth_shackleton = _synthesize_planetary_point(PlanetaryBody.MOON, shackleton.lat, shackleton.lon)
    # Shackleton elevation is 1300m, slope is 24 deg (Malapert is 5000m, Mons Mouton is 6.5 deg)
    assert abs(synth_shackleton["elevation_m"] - shackleton.parameters["elevation_m"]) < 350.0
    assert abs(synth_shackleton["slope_deg"] - shackleton.parameters["slope_deg"]) < 3.0

    # Earth hotspot H3 synthesis must also blend low_sun_grazing_hours
    mcmurdo = next(h for h in EARTH_HOTSPOTS if h.id == "mcmurdo_dry_valleys")
    synth_mcmurdo = _synthesize_earth_cell_parameters(mcmurdo.lat, mcmurdo.lon)
    assert abs(synth_mcmurdo["low_sun_grazing_hours"] - mcmurdo.parameters["low_sun_grazing_hours"]) < 150.0


