"""Whole-Earth evaluation suite auditing all ~87,815 H3 cells in data/processed/."""

from __future__ import annotations

import json
import math
import statistics
import time

import numpy as np
import pytest

from isotopos.api.datastore import get_default_datastore
from isotopos.core.registry import DEFAULT_REGISTRY
from isotopos.etl.sources.baseline_regions import is_well_known_baseline_region
from isotopos.scoring.engine import AnalogScoringEngine

pytestmark = pytest.mark.full_earth

FORBIDDEN_SENTINELS = (-999.0, -888.0, -9999.0, 99999.0)


@pytest.fixture(scope="module")
def earth_audit_context():
    store = get_default_datastore()
    return {
        "store": store,
        "engine": AnalogScoringEngine(DEFAULT_REGISTRY),
        "geojson": store.earth_geojson,
    }


def test_pillar1_whole_earth_data_integrity_and_provenance(earth_audit_context):
    """Pillar 1: Zero NaN/Inf/sentinels, 1:1 H3-to-GeoJSON parity, country tags, and provenance."""
    store = earth_audit_context["store"]
    geojson = earth_audit_context["geojson"]
    sites = store.h3_sites
    features = geojson["features"]

    assert len(sites) >= 87000
    assert len(features) == len(sites)

    site_ids = {s.id for s in sites}
    feat_ids = {f["properties"]["id"] for f in features}
    assert site_ids == feat_ids

    param_ids = [p.id for p in DEFAULT_REGISTRY.parameters]
    countries_populated = 0
    interpolated_cells = 0

    for site in sites:
        if site.country:
            countries_populated += 1
        assert len(site.interpolated_parameters) <= len(param_ids)
        if site.interpolated_parameters:
            interpolated_cells += 1
            for ip in site.interpolated_parameters:
                assert ip in param_ids
        for pid in param_ids:
            val = site.parameters[pid]
            assert math.isfinite(val), f"{site.id} param {pid} is not finite: {val}"
            for sentinel in FORBIDDEN_SENTINELS:
                assert abs(val - sentinel) > 1e-3, f"{site.id} param {pid} leaked sentinel {sentinel}"
        assert site.parameters["magnetic_anomaly_nt"] >= 0.0
        assert site.parameters["slope_deg"] >= 0.0

    # GeoJSON properties carry is_well_known flag consistently with EarthSite
    well_known_geojson = {f["properties"]["id"]: bool(f["properties"].get("is_well_known")) for f in features}
    for site in sites:
        assert well_known_geojson[site.id] == site.is_well_known

    assert countries_populated / len(sites) > 0.90
    # Real coastal/EMAG2 track gaps exist and are tracked transparently (not all 0 or all 100%)
    assert interpolated_cells < len(sites) * 0.25


def _mean_param_in_box(sites, param_id: str, lat_min: float, lat_max: float, lon_min: float, lon_max: float) -> float:
    vals = [
        s.parameters[param_id]
        for s in sites
        if lat_min <= s.lat <= lat_max and lon_min <= s.lon <= lon_max
    ]
    assert vals, f"No H3 cells found inside box ({lat_min}..{lat_max}, {lon_min}..{lon_max})"
    return statistics.fmean(vals)


def test_pillar2_real_geophysical_and_em_landmarks(earth_audit_context):
    """Pillar 2: Real geophysical & EM features match Earth reference landmarks without cave smearing."""
    sites = earth_audit_context["store"].h3_sites

    # EM landmarks: Kursk Magnetic Anomaly & Bangui Anomaly vs global continental median
    global_mag_median = statistics.median(s.parameters["magnetic_anomaly_nt"] for s in sites)
    kursk_mag = _mean_param_in_box(sites, "magnetic_anomaly_nt", 50.0, 53.0, 34.5, 38.5)
    bangui_mag = _mean_param_in_box(sites, "magnetic_anomaly_nt", 3.5, 6.5, 16.5, 20.5)
    assert kursk_mag > max(global_mag_median * 1.4, global_mag_median + 35.0)
    assert bangui_mag > max(global_mag_median * 1.3, global_mag_median + 25.0)

    # Topography: Tibetan Plateau / Himalayas vs Amazon Basin & Netherlands lowlands
    tibet_elev = _mean_param_in_box(sites, "elevation_m", 30.0, 35.0, 82.0, 92.0)
    amazon_elev = _mean_param_in_box(sites, "elevation_m", -5.0, 0.0, -65.0, -55.0)
    assert tibet_elev > 4000.0
    assert amazon_elev < 300.0
    assert tibet_elev - amazon_elev > 3500.0

    # Aridity & exposed regolith: Sahara / Atacama vs Amazon Basin
    sahara_aridity = _mean_param_in_box(sites, "aridity_dryness_index", 20.0, 26.0, 5.0, 15.0)
    amazon_aridity = _mean_param_in_box(sites, "aridity_dryness_index", -4.0, 0.0, -65.0, -58.0)
    sahara_regolith = _mean_param_in_box(sites, "regolith_rock_abundance", 20.0, 26.0, 5.0, 15.0)
    amazon_regolith = _mean_param_in_box(sites, "regolith_rock_abundance", -4.0, 0.0, -65.0, -58.0)
    assert sahara_aridity - amazon_aridity > 0.35
    assert sahara_regolith - amazon_regolith > 0.40

    # East Antarctica real WorldClim temperature & ETOPO elevation (NOT zeroed or permafrost-free)
    antarctica_temp = _mean_param_in_box(sites, "mean_temp_c", -82.0, -72.0, 60.0, 110.0)
    antarctica_elev = _mean_param_in_box(sites, "elevation_m", -82.0, -72.0, 60.0, 110.0)
    assert antarctica_temp < -25.0
    assert antarctica_elev > 1500.0

    # Zero cave smearing: Sicily H3 cells around Etna retain daytime illumination (not cave 0.0)
    sicily_solar = _mean_param_in_box(sites, "solar_illumination_frac", 37.0, 38.2, 13.5, 15.3)
    assert sicily_solar > 0.45


def test_pillar3_no_sinusoidal_em_striping_artifacts(earth_audit_context):
    """Pillar 3: EMAG2v3 anomaly field has natural spatial spectrum rather than artificial sine carrier."""
    sites = earth_audit_context["store"].h3_sites
    # Sample along a long low-latitude continental band in Africa / South America sorted by lon
    band = sorted(
        (s for s in sites if 18.0 <= s.lat <= 20.0 and -12.0 <= s.lon <= 30.0),
        key=lambda s: s.lon,
    )
    assert len(band) >= 40
    vals = np.array([s.parameters["magnetic_anomaly_nt"] for s in band], dtype=np.float64)
    centered = vals - vals.mean()
    # Real crust has broad multi-scale power without >35% of energy concentrated in a single high-freq carrier bin
    spectrum = np.abs(np.fft.rfft(centered)) ** 2
    high_freq_power = spectrum[3:]  # exclude DC & basin-scale trend
    if high_freq_power.sum() > 0:
        peak_concentration = float(high_freq_power.max() / high_freq_power.sum())
        assert peak_concentration < 0.35


def test_pillar4_full_preset_ranking_novelty_mask_and_nfr1_latency(earth_audit_context):
    """Pillar 4: All 12 presets rank in <100ms, novelty exclusion clears all baseline regions, and shifts results."""
    store = earth_audit_context["store"]
    engine = earth_audit_context["engine"]
    h3_pre = store.h3_prepacked
    hs_pre = store.hotspot_prepacked

    changed_presets = 0
    max_elapsed_ms = 0.0

    for preset in store.presets:
        target = store.interpolator.extract_preset(preset.id)
        weights = dict(preset.recommended_weights)

        t0 = time.perf_counter()
        all_eval = engine.evaluate_prepacked(
            prepacked=h3_pre,
            target=target,
            weights=weights,
            exclude_well_known=False,
            top_k=15,
            include_dimension_scores=False,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        max_elapsed_ms = max(max_elapsed_ms, elapsed_ms)

        novel_eval = engine.evaluate_prepacked(
            prepacked=h3_pre,
            target=target,
            weights=weights,
            exclude_well_known=True,
            top_k=15,
            include_dimension_scores=False,
        )
        novel_hs_eval = engine.evaluate_prepacked(
            prepacked=hs_pre,
            target=target,
            weights=weights,
            exclude_well_known=True,
            top_k=15,
            include_dimension_scores=False,
        )

        assert len(all_eval.ranked_results) == 15
        assert len(novel_eval.ranked_results) == 15
        assert len(novel_hs_eval.ranked_results) > 0

        # Zero baseline cells or baseline hotspots may leak into novel rankings
        for r in novel_eval.ranked_results:
            assert r.site.is_well_known is False
            in_baseline, reason = is_well_known_baseline_region(r.site.lat, r.site.lon)
            assert in_baseline is False, f"{preset.id} leaked baseline cell {r.site.id} ({reason})"
        for r in novel_hs_eval.ranked_results:
            assert r.site.is_well_known is False

        ids_all = [r.site.id for r in all_eval.ranked_results]
        ids_novel = [r.site.id for r in novel_eval.ranked_results]
        if ids_all != ids_novel:
            changed_presets += 1

    # Full-region exclusion must materially shift rankings for baseline-dominated targets (e.g., Shackleton / Arcadia)
    assert changed_presets >= 4
    assert max_elapsed_ms < 100.0, f"NFR-1 violation: max scoring latency {max_elapsed_ms:.2f} ms"
