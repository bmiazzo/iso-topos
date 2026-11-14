"""Vectorized analog scoring and divergence explanation engine."""

from isotopos.scoring.engine import AnalogScoringEngine, EvaluationModelSpec, EvaluationResponse
from isotopos.scoring.explainer import DivergenceExplainer
from isotopos.scoring.mission_weights import (
    EvaluationModelDescriber,
    TileVariableModel,
    build_mission_weight_prompt,
    build_tile_variable_models,
    evaluate_mission_weights,
    parse_and_validate_weights,
)
from isotopos.scoring.site_index import PrepackedSiteIndex

__all__ = [
    "AnalogScoringEngine",
    "DivergenceExplainer",
    "EvaluationModelDescriber",
    "EvaluationModelSpec",
    "EvaluationResponse",
    "PrepackedSiteIndex",
    "TileVariableModel",
    "build_mission_weight_prompt",
    "build_tile_variable_models",
    "evaluate_mission_weights",
    "parse_and_validate_weights",
]
