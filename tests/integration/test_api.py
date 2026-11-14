"""Failing-first integration tests for iso-topos FastAPI service layer (FR-2..FR-15, DR-3)."""

from fastapi.testclient import TestClient

from isotopos.api.app import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_metadata_endpoint_returns_dimensions_parameters_and_presets():
    """FR-2, FR-7, DR-3: Metadata endpoint exposes declarative schema, provenance, and presets."""
    client = _client()
    resp = client.get("/api/v1/metadata")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["dimensions"]) == 5
    assert len(data["parameters"]) == 17
    assert len(data["presets"]) == 12
    assert len(data["hotspots"]) == 26
    first_param = data["parameters"][0]
    assert "earth_provenance" in first_param
    assert "moon_provenance" in first_param
    assert "mars_provenance" in first_param


def test_earth_grid_endpoint_returns_geojson():
    """DR-2: Pre-processed Adaptive H3 GeoJSON served cleanly without raw rasters."""
    client = _client()
    resp = client.get("/api/v1/earth-grid")
    assert resp.status_code == 200
    geo = resp.json()
    assert geo["type"] == "FeatureCollection"
    assert len(geo["features"]) > 1000


def test_target_extract_preset_and_arbitrary_coordinate():
    """FR-3 & FR-3b: Preset extraction vs. arbitrary Moon/Mars coordinate extrapolation."""
    client = _client()

    preset_resp = client.post(
        "/api/v1/target/extract",
        json={"preset_id": "mons_mouton"},
    )
    assert preset_resp.status_code == 200
    preset_data = preset_resp.json()
    assert preset_data["is_extrapolated"] is False
    assert preset_data["body"] == "moon"

    arb_resp = client.post(
        "/api/v1/target/extract",
        json={"body": "mars", "lat": 24.5, "lon": -110.2},
    )
    assert arb_resp.status_code == 200
    arb_data = arb_resp.json()
    assert arb_data["is_extrapolated"] is True
    assert len(arb_data["extrapolated_parameters"]) == 17


def test_rank_endpoint_evaluates_sites_and_novelty_filter():
    """FR-6, FR-10, FR-11, NFR-1: Rank endpoint returns cell scores, top H3 cells, and hotspots."""
    client = _client()
    preset = client.post("/api/v1/target/extract", json={"preset_id": "shackleton_rim"}).json()

    resp = client.post(
        "/api/v1/rank",
        json={
            "target": preset,
            "weights": preset["recommended_weights"],
            "mode": "clamped",
            "exclude_well_known": True,
            "top_k": 10,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["all_weights_zero"] is False
    assert len(data["cell_scores"]) > 1000
    assert len(data["top_h3_results"]) == 10
    assert len(data["hotspot_results"]) == 20  # 26 total - 6 well-known baselines
    assert all(not r["site"]["is_well_known"] for r in data["hotspot_results"])
    assert len(data["hotspot_results"][0]["earth_limit_caveats"]) >= 3


def test_export_endpoint_returns_csv_and_json():
    """FR-15: Export ranked analogs as CSV and JSON."""
    client = _client()
    preset = client.post("/api/v1/target/extract", json={"preset_id": "jezero_crater"}).json()
    payload = {
        "target": preset,
        "weights": preset["recommended_weights"],
        "mode": "clamped",
        "exclude_well_known": False,
        "top_k": 5,
    }

    csv_resp = client.post("/api/v1/export?format=csv", json=payload)
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    assert "site_id,site_name,site_type" in csv_resp.text

    json_resp = client.post("/api/v1/export?format=json", json=payload)
    assert json_resp.status_code == 200
    exported = json_resp.json()
    assert len(exported["results"]) >= 5
