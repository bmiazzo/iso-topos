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


def test_single_site_inspection_and_raw_parameter_layer_endpoints():
    """FR-13 & DEC-005: Inspect any H3 cell on the globe and fetch raw parameter layer values."""
    client = _client()
    grid_resp = client.get("/api/v1/earth-grid")
    assert grid_resp.status_code == 200
    first_cell_id = grid_resp.json()["features"][0]["properties"]["id"]

    param_resp = client.get("/api/v1/earth-grid/parameter/elevation_m")
    assert param_resp.status_code == 200
    param_data = param_resp.json()
    assert first_cell_id in param_data["values"]

    preset = client.post("/api/v1/target/extract", json={"preset_id": "shackleton_rim"}).json()
    site_resp = client.post(
        f"/api/v1/site/{first_cell_id}",
        json={
            "target": preset,
            "weights": preset["recommended_weights"],
            "mode": "clamped",
        },
    )
    assert site_resp.status_code == 200
    site_breakdown = site_resp.json()
    assert site_breakdown["site"]["id"] == first_cell_id
    assert "overall_score" in site_breakdown
    assert len(site_breakdown["dimension_breakdowns"]) == 5


def test_weights_evaluate_endpoint_returns_17_weights_from_mission_description():
    """POST /api/v1/weights/evaluate takes mission_description and returns 17 parameter weights."""
    from isotopos.core.registry import DEFAULT_REGISTRY

    fake_weights = {p.id: 0.75 for p in DEFAULT_REGISTRY.parameters}
    fake_weights["biosignature_preservation_score"] = 0.0

    class FakeLLMClient:
        def generate_weights_json(self, system_prompt: str, user_prompt: str, json_schema: dict) -> dict:
            assert "def score_tile_scalar" in system_prompt
            assert "Lunar south pole" in user_prompt
            return fake_weights

    client = TestClient(create_app(llm_client=FakeLLMClient()))
    resp = client.post(
        "/api/v1/weights/evaluate",
        json={"mission_description": "Lunar south pole base extracting subsurface ice in cold traps."},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "weights" in data
    assert len(data["weights"]) == 17
    assert data["weights"]["subsurface_ice_permafrost"] == 0.75
    assert data["weights"]["biosignature_preservation_score"] == 0.0


def test_weights_evaluate_endpoint_returns_503_when_no_api_key_configured(monkeypatch):
    """POST /api/v1/weights/evaluate returns a clear 503 error when no AI API key is configured."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)

    client = _client()
    resp = client.post(
        "/api/v1/weights/evaluate",
        json={"mission_description": "Mars astrobiology rover drilling clay sediments."},
    )
    assert resp.status_code == 503
    assert "API key" in resp.json()["detail"]


def test_frontend_static_modules_and_collapsible_shell_served():
    """Verify index.html and all modular CSS/ES module static files are served with HTTP 200."""
    import re

    client = _client()
    index_resp = client.get("/")
    assert index_resp.status_code == 200
    html = index_resp.text
    assert 'data-collapse-id="target-selection"' in html
    assert 'data-collapse-id="planetary-picker"' in html
    assert 'no-scrollbar' in html

    css_resp = client.get("/static/styles.css")
    assert css_resp.status_code == 200
    for imp in re.findall(r'@import\s+url\("([^"]+)"\)', css_resp.text):
        asset_path = "/static/" + imp.lstrip("./")
        assert client.get(asset_path).status_code == 200, asset_path

    js_routes = [
        "/static/app.js",
        "/static/js/state.js",
        "/static/js/api.js",
        "/static/js/ui/dom.js",
        "/static/js/ui/collapsible.js",
        "/static/js/ui/menu_summaries.js",
        "/static/js/components/starfield.js",
        "/static/js/components/color_scale.js",
        "/static/js/components/globe_map.js",
        "/static/js/components/target_panel.js",
        "/static/js/components/planetary_picker.js",
        "/static/js/components/advanced_panel.js",
        "/static/js/components/breakdown_panel.js",
        "/static/js/components/ai_weights.js",
    ]
    for route in js_routes:
        assert client.get(route).status_code == 200, route


def test_health_and_error_handling_endpoints():
    """Verify /api/v1/health and 400/404 error responses for invalid IDs or payloads."""
    client = _client()
    health_resp = client.get("/api/v1/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "ok"

    assert client.get("/api/v1/earth-grid/parameter/nonexistent_param").status_code == 404
    assert client.post("/api/v1/target/extract", json={"preset_id": "nonexistent"}).status_code == 404
    assert client.post("/api/v1/target/extract", json={"body": "moon"}).status_code == 400

    preset = client.post("/api/v1/target/extract", json={"preset_id": "shackleton_rim"}).json()
    assert client.post("/api/v1/site/unknown_site", json={"target": preset}).status_code == 404



