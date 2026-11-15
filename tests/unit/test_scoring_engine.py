"""Failing-first unit tests for AnalogScoringEngine (FR-6, FR-10, FR-15, ER-1)."""

import pytest

from isotopos.core.models import (
    EarthSite,
    PhysicalFilter,
    PlanetaryBody,
    ScoringMode,
    TargetLocation,
)
from isotopos.core.registry import DEFAULT_REGISTRY
from isotopos.scoring.engine import AnalogScoringEngine, PrepackedSiteIndex


def _make_site(
    site_id: str,
    is_well_known: bool = False,
    overrides: dict[str, float] | None = None,
) -> EarthSite:
    params = {p.id: (p.earth_min + p.earth_max) / 2.0 for p in DEFAULT_REGISTRY.parameters}
    if overrides:
        params.update(overrides)
    return EarthSite(
        id=site_id,
        name=f"Site {site_id}",
        region="Test Region",
        site_type="hotspot",
        lat=66.5,
        lon=-50.0,
        is_well_known=is_well_known,
        feature_category="test",
        parameters=params,
    )


def _make_target(
    body: PlanetaryBody = PlanetaryBody.MOON,
    overrides: dict[str, float] | None = None,
) -> TargetLocation:
    params = {p.id: (p.earth_min + p.earth_max) / 2.0 for p in DEFAULT_REGISTRY.parameters}
    if overrides:
        params.update(overrides)
    return TargetLocation(
        name="Test Target",
        body=body,
        lat=-89.0,
        lon=0.0,
        parameters=params,
    )


def test_exact_match_scores_1_0():
    """Exact match across all active parameters yields overall_score = 1.0."""
    site = _make_site("exact")
    target = _make_target()
    engine = AnalogScoringEngine(DEFAULT_REGISTRY)
    response = engine.evaluate(sites=[site], target=target)
    assert response.all_weights_zero is False
    assert len(response.ranked_results) == 1
    assert response.ranked_results[0].overall_score == pytest.approx(1.0)


def test_disabled_dimension_returns_na_subscore():
    """FR-10: If all parameters in a dimension have weight 0, sub_score is None and status is N/A."""
    site = _make_site("s1")
    target = _make_target()
    weights = DEFAULT_REGISTRY.default_weights()
    for pid in DEFAULT_REGISTRY.parameter_ids_for_dimension("subsurface_biology"):
        weights[pid] = 0.0

    engine = AnalogScoringEngine(DEFAULT_REGISTRY)
    response = engine.evaluate(sites=[site], target=target, weights=weights)
    sub_bio = next(
        d for d in response.ranked_results[0].dimension_breakdowns if d.dimension_id == "subsurface_biology"
    )
    assert sub_bio.sub_score is None
    assert sub_bio.status == "N/A"


def test_all_zero_weights_guard_prevents_division_by_zero():
    """FR-10: Guard against all-zero weights across all parameters."""
    site = _make_site("s1")
    target = _make_target()
    zero_weights = {p.id: 0.0 for p in DEFAULT_REGISTRY.parameters}

    engine = AnalogScoringEngine(DEFAULT_REGISTRY)
    response = engine.evaluate(sites=[site], target=target, weights=zero_weights)
    assert response.all_weights_zero is True
    assert response.ranked_results[0].overall_score == 0.0
    assert all(d.status == "N/A" for d in response.ranked_results[0].dimension_breakdowns)


def test_clamped_vs_strict_mode_for_lunar_cryo_extremes():
    """DEC-004: Clamped mode clamps -180C to Earth min (-58C); Strict mode penalizes full delta."""
    cold_site = _make_site("antarctica", overrides={"mean_temp_c": -55.0})
    lunar_psr = _make_target(overrides={"mean_temp_c": -180.0})
    weights = {p.id: 0.0 for p in DEFAULT_REGISTRY.parameters}
    weights["mean_temp_c"] = 1.0

    engine = AnalogScoringEngine(DEFAULT_REGISTRY)
    clamped = engine.evaluate(
        sites=[cold_site], target=lunar_psr, weights=weights, mode=ScoringMode.CLAMPED
    )
    strict = engine.evaluate(
        sites=[cold_site], target=lunar_psr, weights=weights, mode=ScoringMode.STRICT
    )

    assert clamped.ranked_results[0].overall_score > 0.95
    assert strict.ranked_results[0].overall_score < clamped.ranked_results[0].overall_score
    comp = next(
        c for c in clamped.ranked_results[0].parameter_comparisons if c.parameter_id == "mean_temp_c"
    )
    assert comp.out_of_envelope_delta == pytest.approx(122.0)


def test_physical_range_filters_and_novelty_filter():
    """FR-6 & FR-15: Physical filters and exclude_well_known filter sites accurately."""
    well_known = _make_site("atacama", is_well_known=True, overrides={"slope_deg": 4.0})
    novel_flat = _make_site("qaqortorsuaq", is_well_known=False, overrides={"slope_deg": 6.0})
    novel_steep = _make_site("cliff", is_well_known=False, overrides={"slope_deg": 32.0})
    target = _make_target()

    engine = AnalogScoringEngine(DEFAULT_REGISTRY)
    response = engine.evaluate(
        sites=[well_known, novel_flat, novel_steep],
        target=target,
        filters=[PhysicalFilter(parameter_id="slope_deg", max_value=15.0)],
        exclude_well_known=True,
    )
    ids = [r.site.id for r in response.ranked_results]
    assert ids == ["qaqortorsuaq"]


def test_prepacked_site_index_matches_standard_evaluation_and_supports_single_site():
    """DEC-005 & NFR-1: PrepackedSiteIndex evaluates identically and supports single-site lookup."""
    s1 = _make_site("s1", is_well_known=False, overrides={"slope_deg": 5.0, "mean_temp_c": -20.0})
    s2 = _make_site("s2", is_well_known=True, overrides={"slope_deg": 18.0, "mean_temp_c": 15.0})
    target = _make_target(overrides={"slope_deg": 4.0, "mean_temp_c": -25.0})

    engine = AnalogScoringEngine(DEFAULT_REGISTRY)
    prepacked = PrepackedSiteIndex.from_sites([s1, s2], DEFAULT_REGISTRY)

    std_resp = engine.evaluate(sites=[s1, s2], target=target, top_k=2)
    fast_resp = engine.evaluate_prepacked(
        prepacked=prepacked,
        target=target,
        top_k=2,
        include_dimension_scores=True,
    )
    assert fast_resp.cell_scores == std_resp.cell_scores
    assert fast_resp.ranked_results[0].site.id == std_resp.ranked_results[0].site.id

    single = engine.evaluate_single_site(site=s1, target=target)
    assert single.overall_score == pytest.approx(std_resp.cell_scores["s1"])


def test_strict_mode_differentiates_sites_on_extreme_out_of_envelope_parameters():
    """Strict mode must expand normalization span to cover target extremes instead of zeroing all Earth sites."""
    high_swing_desert = _make_site("lut_desert", overrides={"diurnal_amplitude_c": 35.0, "mean_temp_c": -55.0})
    low_swing_cave = _make_site("cave", overrides={"diurnal_amplitude_c": 3.0, "mean_temp_c": 30.0})
    lunar_target = _make_target(overrides={"diurnal_amplitude_c": 250.0, "mean_temp_c": -180.0})

    weights = {p.id: 0.0 for p in DEFAULT_REGISTRY.parameters}
    weights["diurnal_amplitude_c"] = 1.0
    weights["mean_temp_c"] = 1.0

    engine = AnalogScoringEngine(DEFAULT_REGISTRY)
    strict_resp = engine.evaluate(
        sites=[high_swing_desert, low_swing_cave],
        target=lunar_target,
        weights=weights,
        mode=ScoringMode.STRICT,
    )
    scores_by_id = strict_resp.cell_scores
    assert scores_by_id["lut_desert"] > 0.0
    assert scores_by_id["lut_desert"] > scores_by_id["cave"]


def test_weights_auto_normalize_and_accept_values_above_one():
    """FR-10: Per-parameter weights auto-normalize across active parameters and do not fail when > 1.0."""
    site = _make_site("s1", overrides={"elevation_m": 1000.0, "slope_deg": 10.0})
    target = _make_target(overrides={"elevation_m": 1000.0, "slope_deg": 20.0})

    weights = {p.id: 0.0 for p in DEFAULT_REGISTRY.parameters}
    weights["elevation_m"] = 2.0
    weights["slope_deg"] = 6.0

    engine = AnalogScoringEngine(DEFAULT_REGISTRY)
    resp = engine.evaluate(sites=[site], target=target, weights=weights)
    comps = {c.parameter_id: c for c in resp.ranked_results[0].parameter_comparisons}
    assert comps["elevation_m"].weight == pytest.approx(0.25)
    assert comps["slope_deg"].weight == pytest.approx(0.75)


def test_all_weights_zero_reported_even_when_all_sites_filtered_out():
    """FR-10: all_weights_zero must be True when all weights are 0 even if filters match 0 sites."""
    site = _make_site("s1", overrides={"slope_deg": 25.0})
    target = _make_target()
    zero_weights = {p.id: 0.0 for p in DEFAULT_REGISTRY.parameters}

    engine = AnalogScoringEngine(DEFAULT_REGISTRY)
    resp = engine.evaluate(
        sites=[site],
        target=target,
        weights=zero_weights,
        filters=[PhysicalFilter(parameter_id="slope_deg", max_value=5.0)],
    )
    assert resp.filtered_site_count == 0
    assert resp.all_weights_zero is True


def test_prepacked_and_single_site_do_not_trigger_gc_collect(monkeypatch):
    """Regression test: PrepackedSiteIndex.from_sites and evaluate_single_site must never invoke gc.collect()."""
    import gc
    from isotopos.scoring.site_index import PrepackedSiteIndex

    calls = 0

    def fake_collect(*args, **kwargs):
        nonlocal calls
        calls += 1
        return 0

    monkeypatch.setattr(gc, "collect", fake_collect)
    sites = [
        _make_site("s1", overrides={"elevation_m": 1100.0}),
        _make_site("s2", is_well_known=True, overrides={"elevation_m": 2000.0}),
    ]
    target = _make_target(overrides={"elevation_m": 1000.0})
    engine = AnalogScoringEngine(DEFAULT_REGISTRY)

    pre = PrepackedSiteIndex.from_sites(sites, DEFAULT_REGISTRY)
    res = engine.evaluate_single_site(sites[0], target)
    assert calls == 0
    assert pre.get_parameter_map("elevation_m") == {"s1": 1100.0, "s2": 2000.0}
    assert res.site.id == "s1"


def test_evaluate_prepacked_edge_cases_topk_dimension_filter_and_novel_cache():
    """Verify top_k=0, single dimension_id, unknown filter param, novel caching, and include_cell_scores=False."""
    from isotopos.scoring.site_index import PrepackedSiteIndex

    sites = [
        _make_site("s1", overrides={"elevation_m": 1000.0, "mean_temp_c": -60.0}),
        _make_site("s2", is_well_known=True, overrides={"elevation_m": 1200.0, "mean_temp_c": -50.0}),
        _make_site("s3", overrides={"elevation_m": 2500.0, "mean_temp_c": -10.0}),
    ]
    target = _make_target(overrides={"elevation_m": 1000.0, "mean_temp_c": -60.0})
    pre = PrepackedSiteIndex.from_sites(sites, DEFAULT_REGISTRY)
    engine = AnalogScoringEngine(DEFAULT_REGISTRY)

    # top_k=0 yields no ranked results while still evaluating candidates and cell_scores
    zero_k = engine.evaluate_prepacked(prepacked=pre, target=target, top_k=0)
    assert zero_k.ranked_results == []
    assert set(zero_k.cell_scores.keys()) == {"s1", "s2", "s3"}

    # dimension_id restricts cell_dimension_scores to that single dimension
    dim_only = engine.evaluate_prepacked(
        prepacked=pre,
        target=target,
        dimension_id="temperature_illumination",
    )
    assert set(dim_only.cell_dimension_scores["s1"].keys()) == {"temperature_illumination"}
    assert set(dim_only.model_dump()["cell_scores"].keys()) == {"s1", "s2", "s3"}

    # exclude_well_known filters consistently across repeated calls (cached novel slice)
    novel_a = engine.evaluate_prepacked(prepacked=pre, target=target, exclude_well_known=True, top_k=5)
    novel_b = engine.evaluate_prepacked(prepacked=pre, target=target, exclude_well_known=True, top_k=5)
    assert [r.site.id for r in novel_a.ranked_results] == ["s1", "s3"]
    assert [r.site.id for r in novel_b.ranked_results] == ["s1", "s3"]

    # Unknown filter parameter_id returns empty filtered set cleanly
    unknown_flt = engine.evaluate_prepacked(
        prepacked=pre,
        target=target,
        filters=[PhysicalFilter(parameter_id="nonexistent_param", min_value=0.0)],
    )
    assert unknown_flt.filtered_site_count == 0
    assert unknown_flt.ranked_results == []
    assert unknown_flt.cell_scores == {}

    # include_cell_scores=False returns ranked results without populating cell_scores
    no_cells = engine.evaluate_prepacked(
        prepacked=pre,
        target=target,
        top_k=1,
        include_cell_scores=False,
    )
    assert len(no_cells.ranked_results) == 1
    assert no_cells.ranked_results[0].site.id == "s1"
    assert no_cells.cell_scores == {}


