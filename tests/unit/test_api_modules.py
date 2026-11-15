"""Unit tests for modular API schemas, exporters, and DataStore (ER-1, ER-4, DR-4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isotopos.api.datastore import DataStore, get_default_datastore
from isotopos.api.exporters import EXPORTERS, export_ranked_analogs
from isotopos.core.models import PlanetaryBody, ScoringMode
from isotopos.core.registry import DEFAULT_REGISTRY
from isotopos.etl.catalog_data import EARTH_HOTSPOTS, PLANETARY_PRESETS
from isotopos.scoring.engine import AnalogScoringEngine


def test_exporters_registry_supports_csv_and_json():
    """OCP: Export formats are dispatched via EXPORTERS strategy mapping."""
    assert "csv" in EXPORTERS
    assert "json" in EXPORTERS

    engine = AnalogScoringEngine(DEFAULT_REGISTRY)
    target = PLANETARY_PRESETS[0]
    eval_resp = engine.evaluate(sites=list(EARTH_HOTSPOTS[:3]), target=target, top_k=3)

    csv_resp = export_ranked_analogs(
        fmt="csv",
        target=target,
        mode=ScoringMode.CLAMPED,
        results=eval_resp.ranked_results,
        registry=DEFAULT_REGISTRY,
    )
    assert csv_resp.media_type == "text/csv"
    body_text = csv_resp.body.decode("utf-8")
    assert "site_id,site_name,site_type" in body_text
    assert EARTH_HOTSPOTS[0].id in body_text or EARTH_HOTSPOTS[1].id in body_text

    json_resp = export_ranked_analogs(
        fmt="json",
        target=target,
        mode=ScoringMode.CLAMPED,
        results=eval_resp.ranked_results,
        registry=DEFAULT_REGISTRY,
    )
    payload = json.loads(json_resp.body.decode("utf-8"))
    assert payload["mode"] == "clamped"
    assert len(payload["results"]) == 3

    with pytest.raises(ValueError, match="Unsupported export format"):
        export_ranked_analogs(
            fmt="xml",  # type: ignore[arg-type]
            target=target,
            mode=ScoringMode.CLAMPED,
            results=eval_resp.ranked_results,
            registry=DEFAULT_REGISTRY,
        )


def test_datastore_synthetic_fallback_on_empty_directory(tmp_path: Path):
    """DR-4: DataStore builds a small deterministic fallback index when processed files are absent."""
    store = DataStore(data_dir=tmp_path, fallback_max_cells=25, fallback_step_deg=30.0)
    assert len(store.h3_sites) <= 25
    assert len(store.h3_sites) > 0
    assert len(store.hotspots) == 26
    assert len(store.presets) == 12
    uyuni = next(h for h in store.hotspots if h.id == "salar_de_uyuni")
    assert uyuni.country == "Bolivia"
    assert uyuni.photo_url is not None and uyuni.photo_url.startswith("https://")
    extracted = store.interpolator.extract_coordinate(PlanetaryBody.MOON, lat=0.0, lon=0.0)
    assert extracted.is_extrapolated is True


def test_get_default_datastore_returns_cached_singleton():
    """NFR-1: Default DataStore is loaded once and reused across app instances."""
    s1 = get_default_datastore()
    s2 = get_default_datastore()
    assert s1 is s2


def test_export_empty_results_and_datastore_cached_json_payloads(tmp_path: Path):
    """Empty CSV export preserves headers cleanly and DataStore caches plain + gzip JSON bytes."""
    import gzip
    import json

    store = DataStore(data_dir=tmp_path, fallback_max_cells=12, fallback_step_deg=45.0)
    raw_a, gz_a = store.get_cached_json_payload("earth_grid", lambda: store.earth_geojson)
    raw_b, gz_b = store.get_cached_json_payload("earth_grid", lambda: {"should": "not_recompute"})
    assert raw_a is raw_b
    assert gz_a is gz_b
    assert json.loads(raw_a.decode("utf-8")) == store.earth_geojson
    assert json.loads(gzip.decompress(gz_a).decode("utf-8")) == store.earth_geojson

    target = store.interpolator.extract_preset("shackleton_rim")
    empty_resp = export_ranked_analogs(
        fmt="csv",
        target=target,
        mode="clamped",
        results=[],
        registry=DEFAULT_REGISTRY,
    )
    lines = empty_resp.body.decode("utf-8").strip().splitlines()
    assert len(lines) == 1
    assert "site_id" in lines[0]

