"""Failing-first unit tests for offline ETL, grazing sun physics, H3 grid, and Moon/Mars interpolation."""

import pytest

from isotopos.core.models import PlanetaryBody
from isotopos.core.registry import DEFAULT_REGISTRY
from isotopos.etl.catalog_data import EARTH_HOTSPOTS, PLANETARY_PRESETS
from isotopos.etl.interpolator import PlanetaryGridInterpolator
from isotopos.etl.spatial_builder import (
    build_earth_h3_grid,
    build_planetary_grid,
    compute_grazing_sun_hours,
)
from isotopos.scoring.engine import AnalogScoringEngine


def test_grazing_sun_hours_increases_at_polar_latitudes():
    """parameters.md: Arctic Circle (~66.5N) & polar latitudes have far more 0-5 deg grazing sun hours than tropics."""
    equator = compute_grazing_sun_hours(0.0)
    greenland = compute_grazing_sun_hours(66.5)
    high_arctic = compute_grazing_sun_hours(78.0)
    assert equator < 400.0
    assert greenland > equator * 2.0
    assert high_arctic > equator * 1.5


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
    """FR-4 & DR-2: Adaptive H3 grid builds valid land cells with no antimeridian spikes."""
    sites, geojson = build_earth_h3_grid(max_cells=600)
    assert len(sites) >= 200
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) == len(sites)

    param_ids = {p.id for p in DEFAULT_REGISTRY.parameters}
    for site in sites[:25]:
        assert set(site.parameters.keys()) == param_ids

    for feat in geojson["features"]:
        ring = feat["geometry"]["coordinates"][0]
        lons = [pt[0] for pt in ring]
        lats = [pt[1] for pt in ring]
        assert max(lons) - min(lons) <= 90.0
        assert min(lats) >= -85.0 and max(lats) <= 85.0


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
