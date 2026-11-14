"""Vectorized NumPy analog scoring engine (FR-6, FR-10, FR-15, NFR-1, DEC-005)."""

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


class PrepackedSiteIndex:
    """Pre-packed contiguous NumPy matrix for instantaneous evaluation of ~85,000+ H3 cells."""

    def __init__(
        self,
        sites: list[EarthSite],
        site_ids: list[str],
        earth_mat: np.ndarray,
        well_known_mask: np.ndarray,
        param_col_index: dict[str, int],
    ) -> None:
        self.sites = sites
        self.site_ids = site_ids
        self.site_by_id: dict[str, EarthSite] = {s.id: s for s in sites}
        self.earth_mat = earth_mat
        self.well_known_mask = well_known_mask
        self.param_col_index = param_col_index

    @classmethod
    def from_sites(cls, sites: list[EarthSite], registry: ParameterRegistry) -> PrepackedSiteIndex:
        params = registry.parameters
        n_sites = len(sites)
        n_params = len(params)
        earth_mat = np.zeros((n_sites, n_params), dtype=np.float64)
        well_known_mask = np.zeros(n_sites, dtype=bool)
        site_ids: list[str] = []
        param_col_index = {p.id: j for j, p in enumerate(params)}
        midpoints = [(p.earth_min + p.earth_max) / 2.0 for p in params]
        param_ids = [p.id for p in params]

        for i, site in enumerate(sites):
            site_ids.append(site.id)
            well_known_mask[i] = site.is_well_known
            sp = site.parameters
            for j, pid in enumerate(param_ids):
                earth_mat[i, j] = float(sp.get(pid, midpoints[j]))

        return cls(
            sites=sites,
            site_ids=site_ids,
            earth_mat=earth_mat,
            well_known_mask=well_known_mask,
            param_col_index=param_col_index,
        )

    def get_parameter_map(self, parameter_id: str) -> dict[str, float]:
        col = self.param_col_index[parameter_id]
        vals = np.round(self.earth_mat[:, col], 4).tolist()
        return dict(zip(self.site_ids, vals))


class AnalogScoringEngine:
    """Stateless, vectorized NumPy scoring engine driven by ParameterRegistry."""

    def __init__(self, registry: ParameterRegistry) -> None:
        self._registry = registry
        self._explainer = DivergenceExplainer(registry)

    def _prepare_target_and_weights(
        self,
        target: TargetLocation,
        weights: dict[str, float] | None,
        mode: ScoringMode,
    ) -> tuple[np.ndarray, float, bool, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        params = self._registry.parameters
        n_params = len(params)
        resolved_weights = weights if weights is not None else self._registry.default_weights()
        w_vec = np.array(
            [max(0.0, float(resolved_weights.get(p.id, 0.0))) for p in params],
            dtype=np.float64,
        )
        total_weight = float(w_vec.sum())
        all_weights_zero = total_weight <= 0.0

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

        return w_vec, total_weight, all_weights_zero, spans, raw_target, eff_target, env_deltas

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
        w_vec: np.ndarray,
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
                    weight=round(float(w_vec[j]), 4),
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
        keep = np.ones(n_total, dtype=bool)
        if exclude_well_known:
            keep &= ~prepacked.well_known_mask

        for flt in filters or []:
            col = prepacked.param_col_index.get(flt.parameter_id)
            if col is None:
                keep[:] = False
                break
            col_vals = prepacked.earth_mat[:, col]
            if flt.min_value is not None:
                keep &= col_vals >= flt.min_value
            if flt.max_value is not None:
                keep &= col_vals <= flt.max_value

        active_indices = np.flatnonzero(keep)
        if active_indices.size == 0:
            return EvaluationResponse(
                all_weights_zero=False,
                total_candidates_evaluated=n_total,
                filtered_site_count=0,
            )

        (
            w_vec,
            total_weight,
            all_weights_zero,
            spans,
            raw_target,
            eff_target,
            env_deltas,
        ) = self._prepare_target_and_weights(target, weights, mode)

        sub_mat = prepacked.earth_mat[active_indices]
        sim_mat = np.clip(1.0 - np.abs(sub_mat - eff_target) / spans, 0.0, 1.0)

        if all_weights_zero:
            overall_scores = np.zeros(active_indices.size, dtype=np.float64)
        else:
            overall_scores = (sim_mat @ w_vec) / total_weight

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
                    w_vec=w_vec,
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
