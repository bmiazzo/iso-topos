"""Vectorized NumPy analog scoring engine (FR-6, FR-10, FR-15, NFR-1, DEC-005)."""

from __future__ import annotations

import inspect
import textwrap

import numpy as np
from pydantic import BaseModel, Field

from isotopos.core.models import (
    EarthSite,
    ParameterComparison,
    PhysicalFilter,
    RankedAnalogResult,
    ScoringMode,
    TargetLocation,
)
from isotopos.core.registry import ParameterRegistry
from isotopos.scoring.explainer import DivergenceExplainer
from isotopos.scoring.site_index import PrepackedSiteIndex

__all__ = [
    "AnalogScoringEngine",
    "EvaluationModelSpec",
    "EvaluationResponse",
    "PrepackedSiteIndex",
]


class EvaluationResponse(BaseModel):
    """Result bundle returned by AnalogScoringEngine.evaluate()."""

    all_weights_zero: bool = False
    total_candidates_evaluated: int = 0
    filtered_site_count: int = 0
    ranked_results: list[RankedAnalogResult] = Field(default_factory=list)
    cell_scores: dict[str, float] = Field(default_factory=dict)
    cell_dimension_scores: dict[str, dict[str, float | None]] = Field(default_factory=dict)


class EvaluationModelSpec(BaseModel):
    """Self-describing summary and Python reference of how a scoring engine evaluates tiles."""

    engine_name: str
    mode: ScoringMode
    summary: str
    python_code: str
    dimension_rule: str


class AnalogScoringEngine:
    """Stateless, vectorized NumPy scoring engine driven by ParameterRegistry."""

    def __init__(self, registry: ParameterRegistry) -> None:
        self._registry = registry
        self._explainer = DivergenceExplainer(registry)

    def score_tile_scalar(
        self,
        tile_parameters: dict[str, float],
        target_parameters: dict[str, float],
        weights: dict[str, float],
        mode: ScoringMode = ScoringMode.CLAMPED,
    ) -> float:
        """Evaluate overall similarity in [0.0, 1.0] for a single Earth tile against a target."""
        weighted_sim_sum = 0.0
        total_weight = 0.0

        for p in self._registry.parameters:
            w = max(0.0, float(weights.get(p.id, 0.0)))
            if w <= 0.0:
                continue
            midpoint = (p.earth_min + p.earth_max) / 2.0
            e_val = float(tile_parameters.get(p.id, midpoint))
            t_val = float(target_parameters.get(p.id, midpoint))
            if mode == ScoringMode.CLAMPED:
                t_eff = min(p.earth_max, max(p.earth_min, t_val))
                eff_span = p.span
            else:
                t_eff = t_val
                eff_span = max(p.earth_max, t_val) - min(p.earth_min, t_val)
            sim = max(0.0, min(1.0, 1.0 - abs(e_val - t_eff) / eff_span))
            weighted_sim_sum += w * sim
            total_weight += w

        if total_weight <= 0.0:
            return 0.0
        return weighted_sim_sum / total_weight

    def describe_evaluation_model(self, mode: ScoringMode = ScoringMode.CLAMPED) -> EvaluationModelSpec:
        """Return a live description and Python code of this engine's tile evaluation math."""
        try:
            python_code = textwrap.dedent(inspect.getsource(self.score_tile_scalar)).strip()
        except OSError:
            python_code = (
                "sim[i, j] = clip(1.0 - abs(earth[i, j] - eff_target[j]) / eff_span[j], 0.0, 1.0)\n"
                "overall[i] = sum(w[j] * sim[i, j]) / sum(w[j])"
            )
        mode_desc = (
            "clamped (target values outside [earth_min, earth_max] are clamped to Earth's physical envelope)"
            if mode == ScoringMode.CLAMPED
            else "strict (raw target values are used with joint [min(earth_min, target), max(earth_max, target)] span)"
        )
        return EvaluationModelSpec(
            engine_name=type(self).__name__,
            mode=mode,
            summary=(
                f"Weighted span-normalized L1 similarity in [0.0, 1.0] using {mode_desc}. "
                "Each parameter's weight in [0.0, 1.0] scales its contribution to the weighted mean."
            ),
            python_code=python_code,
            dimension_rule=(
                "Each dimension computes its own weighted mean over its active parameters; "
                "setting all parameters in a dimension to 0.0 marks that dimension N/A (cleanly disabled)."
            ),
        )

    def _prepare_target_and_weights(
        self,
        target: TargetLocation,
        weights: dict[str, float] | None,
        mode: ScoringMode,
    ) -> tuple[np.ndarray, np.ndarray, float, bool, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        params = self._registry.parameters
        n_params = len(params)
        resolved_weights = weights if weights is not None else self._registry.default_weights()
        w_vec = np.array(
            [max(0.0, float(resolved_weights.get(p.id, 0.0))) for p in params],
            dtype=np.float64,
        )
        total_weight = float(w_vec.sum())
        all_weights_zero = total_weight <= 0.0
        norm_w_vec = np.zeros(n_params, dtype=np.float64) if all_weights_zero else (w_vec / total_weight)

        eff_spans = np.zeros(n_params, dtype=np.float64)
        raw_target = np.zeros(n_params, dtype=np.float64)
        eff_target = np.zeros(n_params, dtype=np.float64)
        env_deltas = np.zeros(n_params, dtype=np.float64)

        for j, p in enumerate(params):
            t_val = float(target.parameters.get(p.id, (p.earth_min + p.earth_max) / 2.0))
            raw_target[j] = t_val
            if mode == ScoringMode.CLAMPED:
                clamped_val = min(p.earth_max, max(p.earth_min, t_val))
                eff_target[j] = clamped_val
                eff_spans[j] = p.span
                env_deltas[j] = abs(t_val - clamped_val)
            else:
                eff_target[j] = t_val
                eff_spans[j] = max(p.earth_max, t_val) - min(p.earth_min, t_val)
                env_deltas[j] = max(0.0, p.earth_min - t_val, t_val - p.earth_max)

        return (
            w_vec,
            norm_w_vec,
            total_weight,
            all_weights_zero,
            eff_spans,
            raw_target,
            eff_target,
            env_deltas,
        )

    def _build_ranked_result(
        self,
        site: EarthSite,
        target: TargetLocation,
        earth_row: np.ndarray,
        sim_row: np.ndarray,
        overall_score: float,
        raw_target: np.ndarray,
        eff_target: np.ndarray,
        env_deltas: np.ndarray,
        norm_w_vec: np.ndarray,
    ) -> RankedAnalogResult:
        params = self._registry.parameters
        comparisons: list[ParameterComparison] = []
        for j, p in enumerate(params):
            e_val = float(earth_row[j])
            t_raw = float(raw_target[j])
            t_eff = float(eff_target[j])
            comparisons.append(
                ParameterComparison(
                    parameter_id=p.id,
                    label=p.label,
                    dimension_id=p.dimension_id,
                    unit=p.unit,
                    earth_value=round(e_val, 4),
                    target_value=round(t_raw, 4),
                    effective_target_value=round(t_eff, 4),
                    delta=round(e_val - t_raw, 4),
                    out_of_envelope_delta=round(float(env_deltas[j]), 4),
                    similarity=round(float(sim_row[j]), 4),
                    weight=round(float(norm_w_vec[j]), 4),
                )
            )

        breakdowns, strongest, diverging = self._explainer.build_dimension_breakdowns(comparisons)
        caveats = self._explainer.build_caveats(site, target, comparisons)
        relevance = self._explainer.build_exploration_relevance(site, target)

        return RankedAnalogResult(
            site=site,
            overall_score=round(float(overall_score), 4),
            dimension_breakdowns=breakdowns,
            parameter_comparisons=comparisons,
            strongest_dimensions=strongest,
            diverging_dimensions=diverging,
            earth_limit_caveats=caveats,
            exploration_relevance=relevance,
        )

    def evaluate_single_site(
        self,
        site: EarthSite,
        target: TargetLocation,
        weights: dict[str, float] | None = None,
        mode: ScoringMode = ScoringMode.CLAMPED,
    ) -> RankedAnalogResult:
        """Evaluate a single Earth site (H3 cell or hotspot) on demand for click inspection."""
        resp = self.evaluate(
            sites=[site],
            target=target,
            weights=weights,
            mode=mode,
            top_k=1,
        )
        return resp.ranked_results[0]

    def evaluate_prepacked(
        self,
        prepacked: PrepackedSiteIndex,
        target: TargetLocation,
        weights: dict[str, float] | None = None,
        mode: ScoringMode = ScoringMode.CLAMPED,
        filters: list[PhysicalFilter] | None = None,
        exclude_well_known: bool = False,
        top_k: int | None = 15,
        include_dimension_scores: bool = False,
        dimension_id: str | None = None,
    ) -> EvaluationResponse:
        """Vectorized evaluation over a PrepackedSiteIndex (~85,000 H3 Res 4 cells in <25 ms)."""
        n_total = len(prepacked.sites)
        (
            w_vec,
            norm_w_vec,
            total_weight,
            all_weights_zero,
            eff_spans,
            raw_target,
            eff_target,
            env_deltas,
        ) = self._prepare_target_and_weights(target, weights, mode)

        active_indices = prepacked.filter_indices(
            filters=filters,
            exclude_well_known=exclude_well_known,
        )
        if active_indices.size == 0:
            return EvaluationResponse(
                all_weights_zero=all_weights_zero,
                total_candidates_evaluated=n_total,
                filtered_site_count=0,
            )

        sub_mat = prepacked.earth_mat[active_indices]
        sim_mat = np.clip(1.0 - np.abs(sub_mat - eff_target) / eff_spans, 0.0, 1.0)

        if all_weights_zero:
            overall_scores = np.zeros(active_indices.size, dtype=np.float64)
        else:
            overall_scores = sim_mat @ norm_w_vec

        filtered_ids = [prepacked.site_ids[int(i)] for i in active_indices]
        rounded_scores = np.round(overall_scores, 4).tolist()
        cell_scores = dict(zip(filtered_ids, rounded_scores))

        cell_dimension_scores: dict[str, dict[str, float | None]] = {}
        if include_dimension_scores or dimension_id is not None:
            params = self._registry.parameters
            dim_indices: dict[str, list[int]] = {d.id: [] for d in self._registry.dimensions}
            for j, p in enumerate(params):
                dim_indices[p.dimension_id].append(j)

            target_dims = [dimension_id] if (dimension_id and dimension_id in dim_indices) else list(dim_indices.keys())
            dim_subscore_lists: dict[str, list[float] | None] = {}
            for d_id in target_dims:
                idxs = dim_indices[d_id]
                dim_w = w_vec[idxs]
                dim_w_sum = float(dim_w.sum())
                if dim_w_sum <= 0.0:
                    dim_subscore_lists[d_id] = None
                else:
                    arr = (sim_mat[:, idxs] @ dim_w) / dim_w_sum
                    dim_subscore_lists[d_id] = np.round(arr, 4).tolist()

            for k, sid in enumerate(filtered_ids):
                cell_dimension_scores[sid] = {
                    d_id: (lst[k] if lst is not None else None)
                    for d_id, lst in dim_subscore_lists.items()
                }

        order = np.argsort(-overall_scores, kind="stable")
        if top_k is not None:
            order = order[:top_k]

        ranked_results: list[RankedAnalogResult] = []
        for rank_idx in order:
            k = int(rank_idx)
            orig_idx = int(active_indices[k])
            site = prepacked.sites[orig_idx]
            ranked_results.append(
                self._build_ranked_result(
                    site=site,
                    target=target,
                    earth_row=sub_mat[k],
                    sim_row=sim_mat[k],
                    overall_score=float(overall_scores[k]),
                    raw_target=raw_target,
                    eff_target=eff_target,
                    env_deltas=env_deltas,
                    norm_w_vec=norm_w_vec,
                )
            )

        return EvaluationResponse(
            all_weights_zero=all_weights_zero,
            total_candidates_evaluated=n_total,
            filtered_site_count=int(active_indices.size),
            ranked_results=ranked_results,
            cell_scores=cell_scores,
            cell_dimension_scores=cell_dimension_scores,
        )

    def evaluate(
        self,
        sites: list[EarthSite],
        target: TargetLocation,
        weights: dict[str, float] | None = None,
        mode: ScoringMode = ScoringMode.CLAMPED,
        filters: list[PhysicalFilter] | None = None,
        exclude_well_known: bool = False,
        top_k: int | None = None,
    ) -> EvaluationResponse:
        """Rank a list of Earth sites against a planetary target vector via NumPy."""
        prepacked = PrepackedSiteIndex.from_sites(sites, self._registry)
        return self.evaluate_prepacked(
            prepacked=prepacked,
            target=target,
            weights=weights,
            mode=mode,
            filters=filters,
            exclude_well_known=exclude_well_known,
            top_k=top_k,
            include_dimension_scores=True,
        )
