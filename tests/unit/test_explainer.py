"""Failing-first unit tests for DivergenceExplainer & Earth-limit caveats (FR-11, parameters.md)."""

from isotopos.core.models import (
    EarthSite,
    PlanetaryBody,
    ScoringMode,
    TargetLocation,
)
from isotopos.core.registry import DEFAULT_REGISTRY
from isotopos.scoring.engine import AnalogScoringEngine


def _base_params() -> dict[str, float]:
    return {p.id: (p.earth_min + p.earth_max) / 2.0 for p in DEFAULT_REGISTRY.parameters}


def test_lunar_caveats_include_gravity_vacuum_shadows_and_sublimation():
    """FR-11 & parameters.md: Lunar analogs surface 1/6g, vacuum, pitch-black shadows, and sublimation."""
    site = EarthSite(
        id="white_mountain",
        name="White Mountain / Qaqortorsuaq",
        region="Greenland",
        site_type="hotspot",
        lat=66.5,
        lon=-52.5,
        is_well_known=False,
        feature_category="anorthosite_highland",
        parameters={
            **_base_params(),
            "anorthosite_highland_score": 0.95,
            "low_sun_grazing_hours": 1450.0,
            "mean_temp_c": -6.0,
        },
    )
    target = TargetLocation(
        name="Shackleton Crater Rim",
        body=PlanetaryBody.MOON,
        lat=-89.9,
        lon=0.0,
        parameters={
            **_base_params(),
            "anorthosite_highland_score": 0.95,
            "low_sun_grazing_hours": 2400.0,
            "mean_temp_c": -160.0,
            "subsurface_ice_permafrost": 0.8,
        },
    )

    engine = AnalogScoringEngine(DEFAULT_REGISTRY)
    res = engine.evaluate(sites=[site], target=target, mode=ScoringMode.CLAMPED).ranked_results[0]
    caveat_categories = {c.category for c in res.earth_limit_caveats}
    assert {"gravity", "atmosphere_vacuum", "illumination_scattering", "ice_sublimation", "envelope_exceeded"}.issubset(
        caveat_categories
    )
    assert len(res.exploration_relevance) >= 1


def test_mars_caveats_include_co2_radiation_and_sublimation():
    """FR-11 & parameters.md: Mars analogs surface 0.38g, 6 mbar CO2, radiation, and ice sublimation."""
    site = EarthSite(
        id="batagaika",
        name="Batagaika Megaslump",
        region="Siberia",
        site_type="hotspot",
        lat=67.58,
        lon=134.77,
        is_well_known=False,
        feature_category="permafrost",
        parameters={**_base_params(), "subsurface_ice_permafrost": 0.95},
    )
    target = TargetLocation(
        name="Arcadia Planitia",
        body=PlanetaryBody.MARS,
        lat=39.2,
        lon=188.0,
        parameters={**_base_params(), "subsurface_ice_permafrost": 0.9, "mean_temp_c": -65.0},
    )

    engine = AnalogScoringEngine(DEFAULT_REGISTRY)
    res = engine.evaluate(sites=[site], target=target).ranked_results[0]
    caveat_categories = {c.category for c in res.earth_limit_caveats}
    assert {"gravity", "atmosphere_co2", "radiation", "ice_sublimation"}.issubset(caveat_categories)
    assert len(res.strongest_dimensions) >= 1


def test_disabled_parameters_do_not_trigger_envelope_exceeded_caveat():
    """FR-10 & FR-11: Parameters with weight=0.0 must not appear in envelope_exceeded caveats."""
    site = EarthSite(
        id="test_site",
        name="Test Site",
        region="Earth",
        site_type="hotspot",
        lat=0.0,
        lon=0.0,
        parameters=_base_params(),
    )
    target = TargetLocation(
        name="Extreme Target",
        body=PlanetaryBody.MOON,
        lat=-89.0,
        lon=0.0,
        parameters={**_base_params(), "mean_temp_c": -180.0, "diurnal_amplitude_c": 250.0},
    )
    weights = DEFAULT_REGISTRY.default_weights()
    weights["mean_temp_c"] = 0.0
    weights["diurnal_amplitude_c"] = 0.0

    engine = AnalogScoringEngine(DEFAULT_REGISTRY)
    res = engine.evaluate(sites=[site], target=target, weights=weights).ranked_results[0]
    caveat_categories = {c.category for c in res.earth_limit_caveats}
    assert "envelope_exceeded" not in caveat_categories

