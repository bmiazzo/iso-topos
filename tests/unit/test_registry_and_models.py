"""Failing-first unit tests for declarative ParameterRegistry and domain models (ER-1, FR-7, DR-3)."""

import pytest

from isotopos.core.models import (
    DimensionSpec,
    ParameterSpec,
    PlanetaryBody,
    ProvenanceMetadata,
    TargetLocation,
)
from isotopos.core.registry import DEFAULT_REGISTRY, ParameterRegistry


def test_default_registry_contains_core_and_extensible_dimensions():
    """FR-8 & FR-9: 4 core v1 dimensions + 1 extensible Subsurface/Biology/Ops dimension."""
    dim_ids = {d.id for d in DEFAULT_REGISTRY.dimensions}
    assert {
        "topography",
        "geology",
        "temperature_illumination",
        "water_ice",
        "subsurface_biology",
    }.issubset(dim_ids)


def test_default_registry_has_17_parameters_with_full_provenance():
    """DR-3 & parameters.md: Every parameter carries full Earth and planetary provenance."""
    expected_params = {
        "elevation_m",
        "slope_deg",
        "roughness_index",
        "anorthosite_highland_score",
        "basalt_volcanic_score",
        "clay_carbonate_sediment_score",
        "regolith_rock_abundance",
        "magnetic_anomaly_nt",
        "mean_temp_c",
        "diurnal_amplitude_c",
        "solar_illumination_frac",
        "low_sun_grazing_hours",
        "aridity_dryness_index",
        "subsurface_ice_permafrost",
        "cold_trap_sublimation_index",
        "subsurface_cave_drilling_score",
        "biosignature_preservation_score",
    }
    param_ids = {p.id for p in DEFAULT_REGISTRY.parameters}
    assert param_ids == expected_params

    for param in DEFAULT_REGISTRY.parameters:
        assert param.earth_max > param.earth_min
        for prov in (param.earth_provenance, param.moon_provenance, param.mars_provenance):
            assert prov.agency_mission
            assert prov.dataset_name
            assert prov.url.startswith("http")
            assert prov.unit == param.unit
            assert prov.resolution


def test_registry_is_pluggable_without_core_changes():
    """FR-7: Adding or removing a parameter dynamically updates dimension mapping."""
    custom_dim = DimensionSpec(
        id="aeolian",
        name="Aeolian & Dust",
        description="Wind and dust storm proxies",
    )
    custom_param = ParameterSpec(
        id="dust_flux",
        dimension_id="aeolian",
        label="Dust Storm Frequency",
        unit="index (0-1)",
        earth_min=0.0,
        earth_max=1.0,
        default_weight=0.5,
        earth_provenance=ProvenanceMetadata(
            agency_mission="NASA MODIS",
            dataset_name="MODIS Aerosol Optical Depth",
            url="https://earthdata.nasa.gov/",
            unit="index (0-1)",
            resolution="10 km",
        ),
        moon_provenance=ProvenanceMetadata(
            agency_mission="NASA LADEE",
            dataset_name="LDEX Dust Exosphere",
            url="https://pds.nasa.gov/",
            unit="index (0-1)",
            resolution="Orbital",
        ),
        mars_provenance=ProvenanceMetadata(
            agency_mission="NASA MRO",
            dataset_name="MCS Dust Opacity",
            url="https://pds.nasa.gov/",
            unit="index (0-1)",
            resolution="5 deg",
        ),
    )
    reg = ParameterRegistry(
        dimensions=[*DEFAULT_REGISTRY.dimensions, custom_dim],
        parameters=[*DEFAULT_REGISTRY.parameters, custom_param],
    )
    assert reg.get_parameter("dust_flux").dimension_id == "aeolian"
    assert "dust_flux" in reg.parameter_ids_for_dimension("aeolian")


def test_registry_rejects_duplicate_parameter_ids():
    """Guard against accidental duplicate parameter registration."""
    first = DEFAULT_REGISTRY.parameters[0]
    with pytest.raises(ValueError, match="Duplicate parameter"):
        ParameterRegistry(
            dimensions=DEFAULT_REGISTRY.dimensions,
            parameters=[first, first],
        )


def test_target_location_tracks_extrapolation_flags():
    """FR-3: Arbitrary coordinate extraction tracks extrapolated parameters transparently."""
    target = TargetLocation(
        name="Arbitrary Moon Site",
        body=PlanetaryBody.MOON,
        lat=-88.5,
        lon=12.4,
        parameters={p.id: p.earth_min for p in DEFAULT_REGISTRY.parameters},
        is_extrapolated=True,
        extrapolated_parameters=["elevation_m", "mean_temp_c"],
    )
    assert target.is_extrapolated is True
    assert "mean_temp_c" in target.extrapolated_parameters
