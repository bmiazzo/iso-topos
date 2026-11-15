"""Unit tests for modular tile-variable modeling, engine-driven evaluation prompt generation, and AI weight evaluation (ER-1, FR-7, FR-10)."""

from __future__ import annotations

import json

import httpx
import pytest

from isotopos.core.models import DimensionSpec, ParameterSpec, ScoringMode
from isotopos.core.registry import DEFAULT_REGISTRY, ParameterRegistry
from isotopos.etl.catalog_data import EARTH_HOTSPOTS, PLANETARY_PRESETS
from isotopos.scoring.engine import AnalogScoringEngine, EvaluationModelSpec, PrepackedSiteIndex
from isotopos.scoring.llm_client import (
    GeminiRESTClient,
    LLMConfigurationError,
    LLMProviderError,
    OpenAICompatibleRESTClient,
    resolve_llm_client,
)
from isotopos.scoring.mission_weights import (
    build_mission_weight_prompt,
    build_tile_variable_models,
    evaluate_mission_weights,
    parse_and_validate_weights,
)


def test_build_tile_variable_models_captures_all_17_parameters_and_tile_stats():
    """Each tile variable model captures registry bounds, units, and empirical tile stats."""
    prepacked = PrepackedSiteIndex.from_sites(list(EARTH_HOTSPOTS), DEFAULT_REGISTRY)
    models = build_tile_variable_models(DEFAULT_REGISTRY, prepacked=prepacked)

    assert len(models) == 17
    by_id = {m.id: m for m in models}
    assert set(by_id.keys()) == {p.id for p in DEFAULT_REGISTRY.parameters}

    slope = by_id["slope_deg"]
    assert slope.dimension_id == "topography"
    assert slope.unit == "deg"
    assert slope.earth_min == 0.0
    assert slope.earth_max == 38.0
    assert slope.span == 38.0
    assert slope.tile_min is not None
    assert slope.tile_median is not None
    assert slope.tile_max is not None
    assert slope.tile_std is not None
    assert slope.tile_min <= slope.tile_median <= slope.tile_max
    assert slope.tile_std >= 0.0


@pytest.mark.parametrize("mode", [ScoringMode.CLAMPED, ScoringMode.STRICT])
def test_engine_scalar_score_matches_vectorized_engine(mode: ScoringMode):
    """AnalogScoringEngine.score_tile_scalar matches vectorized evaluate_single_site in both modes."""
    engine = AnalogScoringEngine(DEFAULT_REGISTRY)
    site = EARTH_HOTSPOTS[0]
    preset = PLANETARY_PRESETS[0]
    weights = preset.recommended_weights

    engine_res = engine.evaluate_single_site(site=site, target=preset, weights=weights, mode=mode)
    scalar_score = engine.score_tile_scalar(
        tile_parameters=site.parameters,
        target_parameters=preset.parameters,
        weights=weights,
        mode=mode,
    )

    assert round(scalar_score, 4) == engine_res.overall_score


def test_build_mission_weight_prompt_adapts_to_custom_evaluation_engine():
    """Prompt dynamically embeds whatever evaluation model the scoring engine describes."""

    class CustomQuadraticEngine:
        def describe_evaluation_model(self, mode: ScoringMode = ScoringMode.CLAMPED) -> EvaluationModelSpec:
            return EvaluationModelSpec(
                engine_name="CustomQuadraticEngine",
                mode=mode,
                summary="Quadratic penalty scoring model.",
                python_code="def score_quadratic(tile, target, weights):\n    return 1.0 - sum(weights.values())",
                dimension_rule="Disabled dimensions return N/A.",
            )

    system_prompt, user_prompt, _ = build_mission_weight_prompt(
        mission_description="Evaluate landing site flatness.",
        registry=DEFAULT_REGISTRY,
        engine=CustomQuadraticEngine(),
    )

    assert "CustomQuadraticEngine" in system_prompt
    assert "Quadratic penalty scoring model." in system_prompt
    assert "def score_quadratic(tile, target, weights):" in system_prompt
    assert "Evaluate landing site flatness." in user_prompt


def test_prompt_builder_adapts_when_parameters_are_added_or_removed():
    """FR-7: Adding or removing parameters in ParameterRegistry automatically adapts prompt, schema, and validation."""
    base_param = DEFAULT_REGISTRY.parameters[0]
    custom_dim = DimensionSpec(
        id="aeolian",
        name="Aeolian & Dust",
        description="Wind and dust abrasion.",
        is_core_v1=False,
    )
    custom_param = ParameterSpec(
        id="dust_abrasion_index",
        dimension_id="aeolian",
        label="Dust Abrasion Index",
        unit="index (0-1)",
        earth_min=0.0,
        earth_max=1.0,
        default_weight=0.5,
        description="Abrasive fine dust transport index.",
        earth_provenance=base_param.earth_provenance,
        moon_provenance=base_param.moon_provenance,
        mars_provenance=base_param.mars_provenance,
    )

    # Add a parameter
    added_reg = ParameterRegistry(
        dimensions=[*DEFAULT_REGISTRY.dimensions, custom_dim],
        parameters=[*DEFAULT_REGISTRY.parameters, custom_param],
    )
    sys_added, _, schema_added = build_mission_weight_prompt(
        mission_description="Test dust storm rover seal durability on Mars.",
        registry=added_reg,
    )
    assert "dust_abrasion_index" in sys_added
    assert "dust_abrasion_index" in schema_added["properties"]

    # Remove a parameter (e.g., remove biosignature_preservation_score) and verify zero stale references
    removed_id = "biosignature_preservation_score"
    reduced_params = [p for p in DEFAULT_REGISTRY.parameters if p.id != removed_id]
    reduced_reg = ParameterRegistry(
        dimensions=DEFAULT_REGISTRY.dimensions,
        parameters=reduced_params,
    )
    sys_reduced, _, schema_reduced = build_mission_weight_prompt(
        mission_description="Test lunar regolith excavation.",
        registry=reduced_reg,
    )
    assert removed_id not in sys_reduced
    assert removed_id not in schema_reduced["properties"]
    assert len(schema_reduced["properties"]) == len(reduced_params)


def test_parse_and_validate_weights_clamps_bounds_and_rejects_all_zero():
    """FR-10: Weights are validated to [0.0, 1.0] for all registered parameters and cannot be all zero."""
    raw = {p.id: 0.5 for p in DEFAULT_REGISTRY.parameters}
    raw["subsurface_ice_permafrost"] = 1.4  # clamped to 1.0
    raw["biosignature_preservation_score"] = -0.3  # clamped to 0.0

    validated = parse_and_validate_weights({"weights": raw}, DEFAULT_REGISTRY)
    assert len(validated) == 17
    assert validated["subsurface_ice_permafrost"] == 1.0
    assert validated["biosignature_preservation_score"] == 0.0

    all_zero = {p.id: 0.0 for p in DEFAULT_REGISTRY.parameters}
    with pytest.raises(ValueError, match="All parameter weights cannot be zero"):
        parse_and_validate_weights(all_zero, DEFAULT_REGISTRY)


def test_gemini_and_openai_clients_with_mock_transport(monkeypatch: pytest.MonkeyPatch):
    """GeminiRESTClient and OpenAICompatibleRESTClient parse structured weight JSON via httpx."""
    expected_weights = {p.id: round(0.1 + (idx % 9) * 0.1, 2) for idx, p in enumerate(DEFAULT_REGISTRY.parameters)}

    def gemini_handler(request: httpx.Request) -> httpx.Response:
        assert "generativelanguage.googleapis.com" in str(request.url)
        body = json.loads(request.content.decode("utf-8"))
        assert "systemInstruction" in body
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": json.dumps(expected_weights)}]
                        }
                    }
                ]
            },
        )

    gemini_client = GeminiRESTClient(
        api_key="test-gemini-key",
        model="gemini-2.5-flash",
        transport=httpx.MockTransport(gemini_handler),
    )
    result = evaluate_mission_weights(
        mission_description="Artemis south pole ice drilling mission",
        registry=DEFAULT_REGISTRY,
        llm_client=gemini_client,
    )
    assert result == expected_weights

    def openai_handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/chat/completions")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "```json\n" + json.dumps({"weights": expected_weights}) + "\n```"
                        }
                    }
                ]
            },
        )

    openai_client = OpenAICompatibleRESTClient(
        api_key="test-openai-key",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        transport=httpx.MockTransport(openai_handler),
    )
    result_openai = evaluate_mission_weights(
        mission_description="Mars Jezero rover biosignature mission",
        registry=DEFAULT_REGISTRY,
        llm_client=openai_client,
    )
    assert result_openai == expected_weights

    # Missing keys raise LLMConfigurationError
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    with pytest.raises(LLMConfigurationError):
        resolve_llm_client()

    # Upstream HTTP failure raises LLMProviderError
    err_client = GeminiRESTClient(
        api_key="bad-key",
        transport=httpx.MockTransport(lambda req: httpx.Response(502, text="Bad Gateway")),
    )
    with pytest.raises(LLMProviderError):
        evaluate_mission_weights(
            mission_description="Test failure",
            registry=DEFAULT_REGISTRY,
            llm_client=err_client,
        )


def test_llm_client_validation_errors_and_env_resolution(monkeypatch):
    """Cover Gemini/OpenAI HTTP exceptions, malformed payloads, empty keys, and env selection."""
    import httpx
    from isotopos.scoring.llm_client import (
        GeminiRESTClient,
        LLMConfigurationError,
        LLMProviderError,
        OpenAICompatibleRESTClient,
        resolve_llm_client,
    )

    with pytest.raises(LLMConfigurationError):
        GeminiRESTClient(api_key="   ")

    # Malformed Gemini payload -> LLMProviderError
    malformed_gem = GeminiRESTClient(
        api_key="k",
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"candidates": []})),
    )
    with pytest.raises(LLMProviderError):
        malformed_gem.generate_weights_json("sys", "usr", {})

    # Network error in Gemini -> LLMProviderError
    def _raise_http(req):
        raise httpx.ConnectError("offline", request=req)

    offline_gem = GeminiRESTClient(api_key="k", transport=httpx.MockTransport(_raise_http))
    with pytest.raises(LLMProviderError):
        offline_gem.generate_weights_json("sys", "usr", {})

    # OpenAI error paths (401, empty choices, ConnectError)
    for handler in [
        lambda req: httpx.Response(401, text="Unauthorized"),
        lambda req: httpx.Response(200, json={"choices": []}),
        _raise_http,
    ]:
        oa = OpenAICompatibleRESTClient(api_key="k", transport=httpx.MockTransport(handler))
        with pytest.raises(LLMProviderError):
            oa.generate_weights_json("sys", "usr", {})

    # Environment variable resolution selects Gemini vs OpenAI cleanly
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    assert isinstance(resolve_llm_client(), GeminiRESTClient)

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "o-key")
    assert isinstance(resolve_llm_client(), OpenAICompatibleRESTClient)

