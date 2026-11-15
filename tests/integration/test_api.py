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
        "/static/js/planetary_page.js",
        "/static/styles/planetary.css",
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


def test_planetary_selector_page_served_with_html():
    """GET /planetary serves the 3D Moon/Mars interactive coordinate selector HTML page."""
    client = _client()
    resp = client.get("/planetary")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Mars" in resp.text and "Moon" in resp.text


def test_planetary_grid_parameter_endpoint_returns_grid_and_rejects_unknown():
    """GET /api/v1/planetary-grid/{body}/parameter/{param_id} returns Moon/Mars parameter rasters and 404s unknown IDs."""
    client = _client()
    moon_resp = client.get("/api/v1/planetary-grid/moon/parameter/elevation_m")
    assert moon_resp.status_code == 200
    moon_data = moon_resp.json()
    assert moon_data["body"] == "moon"
    assert moon_data["parameter_id"] == "elevation_m"
    assert len(moon_data["lats"]) > 5
    assert len(moon_data["lons"]) > 5
    assert len(moon_data["values"]) == len(moon_data["lats"])

    mars_resp = client.get("/api/v1/planetary-grid/mars/parameter/subsurface_ice_permafrost")
    assert mars_resp.status_code == 200
    assert mars_resp.json()["body"] == "mars"

    mars_mag = client.get("/api/v1/planetary-grid/mars/parameter/magnetic_anomaly_nt")
    assert mars_mag.status_code == 200
    assert len(mars_mag.json()["values"]) == len(mars_mag.json()["lats"])

    assert client.get("/api/v1/planetary-grid/moon/parameter/nonexistent_param").status_code == 404


def test_rank_dimension_filter_and_excluded_counts():
    """POST /api/v1/rank with dimension_id returns per-cell dimension scores and well-known exclusion counts."""
    client = _client()
    preset = client.post("/api/v1/target/extract", json={"preset_id": "jezero_crater"}).json()
    resp = client.post(
        "/api/v1/rank",
        json={
            "target": preset,
            "weights": preset["recommended_weights"],
            "mode": "clamped",
            "dimension_id": "geology",
            "exclude_well_known": True,
            "top_k": 5,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["cell_dimension_scores"]
    assert set(data["cell_dimension_scores"].keys()) == set(data["cell_scores"].keys())
    assert data["excluded_well_known_hotspot_count"] == 6
    assert data["excluded_well_known_h3_count"] >= 0
    for r in data["top_h3_results"]:
        assert r["site"]["is_well_known"] is False
        assert r["site"]["lat"] > -60.0


def test_site_inspect_includes_country_provenance_and_photo_url():
    """POST /api/v1/site/{id} exposes country, interpolated_parameters, and Wikimedia photo URLs on hotspots."""
    client = _client()
    preset = client.post("/api/v1/target/extract", json={"preset_id": "jezero_crater"}).json()
    resp = client.post(
        "/api/v1/site/salar_de_uyuni",
        json={"target": preset, "weights": preset["recommended_weights"], "mode": "clamped"},
    )
    assert resp.status_code == 200
    site = resp.json()["site"]
    assert site["country"] == "Bolivia"
    assert isinstance(site["interpolated_parameters"], list)
    assert site["photo_url"] and site["photo_url"].startswith("https://")
    assert site["photo_attribution"]


def test_frontend_accessibility_and_scientific_chrome():
    """Verify semantic dark color-scheme meta, skip links, table headers, and live regions via HTML parsing."""
    from html.parser import HTMLParser

    class _StructureInspector(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.ids: set[str] = set()
            self.skip_hrefs: set[str] = set()
            self.col_headers: list[str] = []
            self.has_dark_meta = False
            self._in_col_th = False

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            attr_map = dict(attrs)
            el_id = attr_map.get("id")
            if el_id:
                self.ids.add(el_id)
            if tag == "meta" and attr_map.get("name") == "color-scheme" and attr_map.get("content") == "dark":
                self.has_dark_meta = True
            if tag == "a" and "skip-link" in (attr_map.get("class") or ""):
                href = attr_map.get("href")
                if href:
                    self.skip_hrefs.add(href)
            if tag == "th" and attr_map.get("scope") == "col":
                self._in_col_th = True

        def handle_endtag(self, tag: str) -> None:
            if tag == "th":
                self._in_col_th = False

        def handle_data(self, data: str) -> None:
            if self._in_col_th and data.strip():
                self.col_headers.append(data.strip())

    client = _client()
    for path, expected_stage_id, expected_ids in [
        ("/", "main-stage", {"filter-validation-error", "a11y-announcer"}),
        ("/planetary", "planetary-stage", {"a11y-announcer"}),
    ]:
        inspector = _StructureInspector()
        inspector.feed(client.get(path).text)
        assert inspector.has_dark_meta is True
        assert f"#{expected_stage_id}" in inspector.skip_hrefs
        assert expected_stage_id in inspector.ids
        assert expected_ids.issubset(inspector.ids)
        assert "Parameter" in inspector.col_headers


def test_weights_evaluate_error_status_mapping_and_earth_grid_encoding():
    """Verify 503/502/422 error mapping on /weights/evaluate and gzip/identity caching on /earth-grid."""
    from isotopos.api.datastore import get_default_datastore
    from isotopos.scoring.llm_client import LLMConfigurationError, LLMProviderError

    class _FailingLLM:
        def __init__(self, exc: Exception) -> None:
            self._exc = exc

        def generate_weights_json(
            self,
            system_prompt: str,
            user_prompt: str,
            json_schema: dict,
        ) -> dict:
            raise self._exc

    store = get_default_datastore()
    for exc, expected_status in [
        (LLMConfigurationError("missing api key"), 503),
        (LLMProviderError("upstream timeout"), 502),
        (ValueError("bad model output"), 422),
    ]:
        client = TestClient(create_app(store=store, llm_client=_FailingLLM(exc)))
        resp = client.post(
            "/api/v1/weights/evaluate",
            json={"mission_description": "Lunar south pole ISRU mission"},
        )
        assert resp.status_code == expected_status

    # Verify /earth-grid serves identical GeoJSON with both gzip and identity encodings
    shared_client = TestClient(create_app(store=store))
    r_gz = shared_client.get("/api/v1/earth-grid", headers={"Accept-Encoding": "gzip"})
    r_raw = shared_client.get("/api/v1/earth-grid", headers={"Accept-Encoding": "identity"})
    assert r_gz.status_code == 200
    assert r_raw.status_code == 200
    assert len(r_gz.json()["features"]) == len(r_raw.json()["features"])


def test_cached_json_endpoints_return_etag_cache_control_and_304():
    """Verify /api/v1/earth-grid and /api/v1/metadata emit Cache-Control/ETag and honor If-None-Match."""
    client = _client()
    for path in ["/api/v1/metadata", "/api/v1/earth-grid"]:
        resp = client.get(path)
        assert resp.status_code == 200
        etag = resp.headers.get("etag")
        cache_control = resp.headers.get("cache-control")
        assert etag
        assert cache_control and "max-age=" in cache_control

        resp_304 = client.get(path, headers={"If-None-Match": etag})
        assert resp_304.status_code == 304
        assert resp_304.headers.get("etag") == etag
        assert resp_304.content == b""


