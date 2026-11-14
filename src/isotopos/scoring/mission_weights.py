"""Modular tile-variable modeling, engine-driven evaluation prompt builder, and AI weight evaluation."""

from __future__ import annotations

from typing import Any, Protocol

import numpy as np
from pydantic import BaseModel

from isotopos.core.models import ScoringMode
from isotopos.core.registry import DEFAULT_REGISTRY, ParameterRegistry
from isotopos.scoring.engine import AnalogScoringEngine, EvaluationModelSpec, PrepackedSiteIndex
from isotopos.scoring.llm_client import LLMClient, resolve_llm_client


class EvaluationModelDescriber(Protocol):
    """Protocol for any scoring engine that can describe its evaluation model for prompting."""

    def describe_evaluation_model(self, mode: ScoringMode = ScoringMode.CLAMPED) -> EvaluationModelSpec:
        """Return a self-describing summary and Python reference of the scoring math."""


class TileVariableModel(BaseModel):
    """Models a single physical variable stored on each Earth tile (H3 cell or hotspot)."""

    id: str
    dimension_id: str
    dimension_name: str
    label: str
    unit: str
    earth_min: float
    earth_max: float
    span: float
    default_weight: float
    description: str
    tile_min: float | None = None
    tile_median: float | None = None
    tile_max: float | None = None
    tile_std: float | None = None


def build_tile_variable_models(
    registry: ParameterRegistry = DEFAULT_REGISTRY,
    prepacked: PrepackedSiteIndex | None = None,
) -> list[TileVariableModel]:
    """Model all registered variables for each tile along with empirical Earth tile statistics."""
    models: list[TileVariableModel] = []
    has_tiles = prepacked is not None and prepacked.earth_mat.shape[0] > 0

    for p in registry.parameters:
        dim = registry.get_dimension(p.dimension_id)
        tile_min: float | None = None
        tile_median: float | None = None
        tile_max: float | None = None
        tile_std: float | None = None

        if has_tiles and prepacked is not None and p.id in prepacked.param_col_index:
            col = prepacked.param_col_index[p.id]
            col_vals = prepacked.earth_mat[:, col]
            tile_min = round(float(np.min(col_vals)), 4)
            tile_median = round(float(np.median(col_vals)), 4)
            tile_max = round(float(np.max(col_vals)), 4)
            tile_std = round(float(np.std(col_vals)), 4)

        models.append(
            TileVariableModel(
                id=p.id,
                dimension_id=p.dimension_id,
                dimension_name=dim.name,
                label=p.label,
                unit=p.unit,
                earth_min=p.earth_min,
                earth_max=p.earth_max,
                span=p.span,
                default_weight=p.default_weight,
                description=p.description,
                tile_min=tile_min,
                tile_median=tile_median,
                tile_max=tile_max,
                tile_std=tile_std,
            )
        )

    return models


def build_weights_json_schema(registry: ParameterRegistry = DEFAULT_REGISTRY) -> dict[str, Any]:
    """Build strict JSON schema requiring a float weight in [0.0, 1.0] for each registered parameter."""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for p in registry.parameters:
        properties[p.id] = {
            "type": "NUMBER",
            "description": f"Weight in [0.0, 1.0] for {p.label} ({p.unit}).",
        }
        required.append(p.id)
    return {
        "type": "OBJECT",
        "properties": properties,
        "required": required,
    }


def build_mission_weight_prompt(
    mission_description: str,
    registry: ParameterRegistry = DEFAULT_REGISTRY,
    prepacked: PrepackedSiteIndex | None = None,
    engine: EvaluationModelDescriber | None = None,
    mode: ScoringMode = ScoringMode.CLAMPED,
) -> tuple[str, str, dict[str, Any]]:
    """Dynamically structure the system prompt, user prompt, and JSON schema from registry & scoring engine."""
    active_engine: EvaluationModelDescriber = engine if engine is not None else AnalogScoringEngine(registry)
    eval_spec = active_engine.describe_evaluation_model(mode=mode)

    tile_vars = build_tile_variable_models(registry=registry, prepacked=prepacked)
    vars_by_dim: dict[str, list[TileVariableModel]] = {}
    for v in tile_vars:
        vars_by_dim.setdefault(v.dimension_id, []).append(v)

    dim_blocks: list[str] = []
    for dim in registry.dimensions:
        dim_vars = vars_by_dim.get(dim.id, [])
        if not dim_vars:
            continue
        lines = [f"### Dimension `{dim.id}` — {dim.name}", f"Description: {dim.description}"]
        for v in dim_vars:
            stats_str = ""
            if v.tile_min is not None:
                stats_str = (
                    f" | Earth tiles: min={v.tile_min}, median={v.tile_median}, "
                    f"max={v.tile_max}, std={v.tile_std}"
                )
            lines.append(
                f"- `{v.id}` ({v.label}, unit: `{v.unit}`): "
                f"Earth envelope=[{v.earth_min}, {v.earth_max}] (span={v.span}), "
                f"default_weight={v.default_weight}{stats_str}. "
                f"Meaning: {v.description}"
            )
        dim_blocks.append("\n".join(lines))

    variables_section = "\n\n".join(dim_blocks)
    param_keys_list = ", ".join(f'"{p.id}"' for p in registry.parameters)

    system_prompt = (
        "You are a planetary science & mission planning weight calibration model for `iso-topos`.\n"
        "Your task is to read the user's textual mission description and return the optimal weight "
        "in [0.0, 1.0] for each of the registered tile parameters.\n\n"
        f"## 1. How Each Earth Tile Is Evaluated in Python ({eval_spec.engine_name}, mode={eval_spec.mode.value})\n"
        f"{eval_spec.summary}\n\n"
        f"```python\n{eval_spec.python_code}\n```\n\n"
        f"{eval_spec.dimension_rule}\n\n"
        f"## 2. Modeled Variables for Each Tile ({len(tile_vars)} parameters)\n"
        f"{variables_section}\n\n"
        "## 3. Weight Assignment Rules\n"
        "- Assign a float weight between `0.0` and `1.0` for EVERY registered parameter ID.\n"
        "- `0.0`: Irrelevant or non-applicable to the described mission (setting all parameters in a "
        "dimension to `0.0` cleanly disables that dimension).\n"
        "- `0.15` to `0.35`: Low/background relevance.\n"
        "- `0.40` to `0.70`: Moderate operational or environmental relevance.\n"
        "- `0.75` to `1.00`: Primary mission-critical requirement that must strongly drive Earth tile ranking.\n"
        "- At least one parameter must have a positive weight (> 0.0).\n"
        "- Output ONLY a valid JSON object whose keys are the exact parameter IDs "
        f"({param_keys_list}) and whose values are numbers in [0.0, 1.0]."
    )

    user_prompt = f"Mission description:\n{mission_description.strip()}"
    json_schema = build_weights_json_schema(registry=registry)
    return system_prompt, user_prompt, json_schema


def parse_and_validate_weights(
    raw_payload: dict[str, Any],
    registry: ParameterRegistry = DEFAULT_REGISTRY,
) -> dict[str, float]:
    """Validate and normalize AI-returned weights into a complete {param_id: float} dict in [0.0, 1.0]."""
    candidate = raw_payload.get("weights") if isinstance(raw_payload.get("weights"), dict) else raw_payload
    if not isinstance(candidate, dict):
        raise ValueError("Expected a JSON object mapping parameter IDs to float weights.")

    validated: dict[str, float] = {}
    for p in registry.parameters:
        raw_val = candidate.get(p.id, p.default_weight)
        try:
            val = float(raw_val)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid numeric weight for parameter '{p.id}': {raw_val!r}") from exc
        clamped = min(1.0, max(0.0, val))
        validated[p.id] = round(clamped, 2)

    if sum(validated.values()) <= 0.0:
        raise ValueError("All parameter weights cannot be zero.")

    return validated


def evaluate_mission_weights(
    mission_description: str,
    registry: ParameterRegistry = DEFAULT_REGISTRY,
    prepacked: PrepackedSiteIndex | None = None,
    engine: EvaluationModelDescriber | None = None,
    mode: ScoringMode = ScoringMode.CLAMPED,
    llm_client: LLMClient | None = None,
) -> dict[str, float]:
    """Build the prompt from the active registry & scoring engine, call the AI model, and return weights."""
    client = llm_client if llm_client is not None else resolve_llm_client()
    system_prompt, user_prompt, json_schema = build_mission_weight_prompt(
        mission_description=mission_description,
        registry=registry,
        prepacked=prepacked,
        engine=engine,
        mode=mode,
    )
    raw_json = client.generate_weights_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        json_schema=json_schema,
    )
    return parse_and_validate_weights(raw_json, registry=registry)
