"""Vectorized NumPy analog scoring engine (FR-6, FR-10, FR-15, NFR-1)."""

from __future__ import annotations

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


class EvaluationResponse(BaseModel):
    """Result bundle returned by AnalogScoringEngine.evaluate()."""

    all_weights_zero: bool = False
    total_candidates_evaluated: int = 0
    filtered_site_count: int = 0
    ranked_results: list[RankedAnalogResult] = Field(default_factory=list)
    cell_scores: dict[str, float] = Field(default_factory=dict)
    cell_dimension_scores: dict[str, dict[str, float | None]] = Field(default_factory=dict)


class AnalogScoringEngine:
    """Stateless, vectorized NumPy scoring engine driven by ParameterRegistry."""

    def __init__(self, registry: ParameterRegistry) -> None:
        self._registry = registry
        self._explainer = DivergenceExplainer(registry)

    def _apply_filters(
        self,
        sites: list[EarthSite],
        filters: list[PhysicalFilter] | None,
        exclude_well_known: bool,
    ) -> list[EarthSite]:
        filtered: list[EarthSite] = []
        active_filters = filters or []
        for site in sites:
            if exclude_well_known and site.is_well_known:
                continue
            passed = True
            for flt in active_filters:
                val = site.parameters.get(flt.parameter_id)
                if val is None:
                    passed = False
                    break
                if flt.min_value is not None and val < flt.min_value:
                    passed = False
                    break
                if flt.max_value is not None and val > flt.max_value:
                    passed = False
                    break
            if passed:
                filtered.append(site)
        return filtered

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
        """Rank Earth sites against a planetary target vector in <10 ms via NumPy."""
        filtered_sites = self._apply_filters(sites, filters, exclude_well_known)
        if not filtered_sites:
            return EvaluationResponse(
                all_weights_zero=False,
                total_candidates_evaluated=len(sites),
                filtered_site_count=0,
            )

        params = self._registry.parameters
        n_sites = len(filtered_sites)
        n_params = len(params)

        resolved_weights = weights if weights is not None else self._registry.default_weights()
        w_vec = np.array(
            [max(0.0, float(resolved_weights.get(p.id, 0.0))) for p in params],
            dtype=np.float64,
        )
        total_weight = float(w_vec.sum())
        all_weights_zero = total_weight <= 0.0

        # Build Earth matrix (n_sites x n_params) and target reference vectors
        earth_mat = np.zeros((n_sites, n_params), dtype=np.float64)
        spans = np.array([p.span for p in params], dtype=np.float64)
        raw_target = np.zeros(n_params, dtype=np.float64)
        eff_target = np.zeros(n_params, dtype=np.float64)
        env_deltas = np.zeros(n_params, dtype=np.float64)

        for j, p in enumerate(params):
            t_val = float(target.parameters.get(p.id, (p.earth_min + p.earth_max) / 2.0))
            raw_target[j] = t_val
            if mode == ScoringMode.CLAMPED:
                clamped_val = min(p.earth_max, max(p.earth_min, t_val))
                eff_target[j] = clamped_val
                env_deltas[j] = abs(t_val - clamped_val)
            else:
                eff_target[j] = t_val
                env_deltas[j] = max(0.0, p.earth_min - t_val, t_val - p.earth_max)

        for i, site in enumerate(filtered_sites):
            for j, p in enumerate(params):
                earth_mat[i, j] = float(site.parameters.get(p.id, eff_target[j]))

        # Vectorized similarity calculation
        sim_mat = np.clip(1.0 - np.abs(earth_mat - eff_target) / spans, 0.0, 1.0)

        if all_weights_zero:
            overall_scores = np.zeros(n_sites, dtype=np.float64)
        else:
            overall_scores = (sim_mat @ w_vec) / total_weight

        # Precompute per-dimension sub-scores for all sites (used for 3D Globe layer switcher)
        dim_indices: dict[str, list[int]] = {d.id: [] for d in self._registry.dimensions}
        for j, p in enumerate(params):
            dim_indices[p.dimension_id].append(j)

        cell_scores: dict[str, float] = {}
        cell_dimension_scores: dict[str, dict[str, float | None]] = {}

        dim_subscore_arrays: dict[str, np.ndarray | None] = {}
        for dim_id, idxs in dim_indices.items():
            dim_w = w_vec[idxs]
            dim_w_sum = float(dim_w.sum())
            if dim_w_sum <= 0.0:
                dim_subscore_arrays[dim_id] = None
            else:
                dim_subscore_arrays[dim_id] = (sim_mat[:, idxs] @ dim_w) / dim_w_sum

        for i, site in enumerate(filtered_sites):
            cell_scores[site.id] = round(float(overall_scores[i]), 4)
            cell_dimension_scores[site.id] = {
                dim_id: (round(float(arr[i]), 4) if arr is not None else None)
                for dim_id, arr in dim_subscore_arrays.items()
            }

        # Sort descending by overall score
        order = np.argsort(-overall_scores, kind="stable")
        if top_k is not None:
            order = order[:top_k]

        ranked_results: list[RankedAnalogResult] = []
        for idx in order:
            site = filtered_sites[int(idx)]
            comparisons: list[ParameterComparison] = []
            for j, p in enumerate(params):
                e_val = float(earth_mat[int(idx), j])
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
                        similarity=round(float(sim_mat[int(idx), j]), 4),
                        weight=round(float(w_vec[j]), 4),
                    )
                )

            breakdowns, strongest, diverging = self._explainer.build_dimension_breakdowns(comparisons)
            caveats = self._explainer.build_caveats(site, target, comparisons)
            relevance = self._explainer.build_exploration_relevance(site, target)

            ranked_results.append(
                RankedAnalogResult(
                    site=site,
                    overall_score=round(float(overall_scores[int(idx)]), 4),
                    dimension_breakdowns=breakdowns,
                    parameter_comparisons=comparisons,
                    strongest_dimensions=strongest,
                    diverging_dimensions=diverging,
                    earth_limit_caveats=caveats,
                    exploration_relevance=relevance,
                )
            )

        return EvaluationResponse(
            all_weights_zero=all_weights_zero,
            total_candidates_evaluated=len(sites),
            filtered_site_count=len(filtered_sites),
            ranked_results=ranked_results,
            cell_scores=cell_scores,
            cell_dimension_scores=cell_dimension_scores,
        )
