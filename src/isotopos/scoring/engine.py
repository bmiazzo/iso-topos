"""Vectorized NumPy analog scoring engine (FR-6, FR-10, FR-15, NFR-1, DEC-005)."""

from __future__ import annotations

import inspect
import textwrap
from collections import deque
from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, computed_field

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

_SCORE_CHUNK_ROWS = 4096


def _build_cell_scores_dict(
    site_ids: Sequence[str],
    scores: np.ndarray,
    template: dict[str, float] | None = None,
) -> dict[str, float]:
    """Materialize {site_id: rounded_score} dict from pre-evaluated NumPy array."""
    rounded = np.round(scores, 4).tolist()
    if template is not None and len(template) == len(site_ids):
        out = template.copy()
        deque(map(out.__setitem__, site_ids, rounded), maxlen=0)
        return out
    return dict(zip(site_ids, rounded))


class EvaluationResponse(BaseModel):
    """Result bundle returned by AnalogScoringEngine.evaluate()."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    all_weights_zero: bool = False
    total_candidates_evaluated: int = 0
    filtered_site_count: int = 0
    ranked_results: list[RankedAnalogResult] = Field(default_factory=list)
    cell_dimension_scores: dict[str, dict[str, float | None]] = Field(default_factory=dict)

    _cell_scores_cache: dict[str, float] | None = PrivateAttr(default=None)
    _lazy_site_ids: Sequence[str] | None = PrivateAttr(default=None)
    _lazy_scores_arr: np.ndarray | None = PrivateAttr(default=None)
    _lazy_template: dict[str, float] | None = PrivateAttr(default=None)
    _lazy_template_fn: Callable[[], dict[str, float] | None] | None = PrivateAttr(default=None)

    def __init__(self, *, cell_scores: dict[str, float] | None = None, **data: Any) -> None:
        super().__init__(**data)
        if cell_scores is not None:
            self._cell_scores_cache = dict(cell_scores)

    @computed_field
    @property
    def cell_scores(self) -> dict[str, float]:
        """Materialize and cache {site_id: rounded_score} on first access."""
        if self._cell_scores_cache is None:
            if self._lazy_site_ids is not None and self._lazy_scores_arr is not None:
                tpl = self._lazy_template
                if tpl is None and self._lazy_template_fn is not None:
                    tpl = self._lazy_template_fn()
                self._cell_scores_cache = _build_cell_scores_dict(
                    self._lazy_site_ids,
                    self._lazy_scores_arr,
                    tpl,
                )
                self._lazy_site_ids = None
                self._lazy_scores_arr = None
                self._lazy_template = None
                self._lazy_template_fn = None
            else:
                self._cell_scores_cache = {}
        return self._cell_scores_cache

    @classmethod
    def from_scores(
        cls,
        *,
        all_weights_zero: bool,
        total_candidates_evaluated: int,
        filtered_site_count: int,
        ranked_results: list[RankedAnalogResult],
        cell_dimension_scores: dict[str, dict[str, float | None]],
        site_ids: Sequence[str] | None = None,
        overall_scores: np.ndarray | None = None,
        dict_template: dict[str, float] | None = None,
        dict_template_fn: Callable[[], dict[str, float] | None] | None = None,
        include_cell_scores: bool = True,
    ) -> EvaluationResponse:
        """Construct an EvaluationResponse, deferring large dict allocation until read."""
        resp = cls.model_construct(
            all_weights_zero=all_weights_zero,
            total_candidates_evaluated=total_candidates_evaluated,
            filtered_site_count=filtered_site_count,
            ranked_results=ranked_results,
            cell_dimension_scores=cell_dimension_scores,
        )
        if include_cell_scores and site_ids is not None and overall_scores is not None:
            if len(site_ids) < 2048:
                tpl = (
                    dict_template
                    if dict_template is not None
                    else (dict_template_fn() if dict_template_fn is not None else None)
                )
                resp._cell_scores_cache = _build_cell_scores_dict(
                    site_ids, overall_scores, tpl
                )
            else:
                resp._lazy_site_ids = site_ids
                resp._lazy_scores_arr = overall_scores
                resp._lazy_template = dict_template
                resp._lazy_template_fn = dict_template_fn
        else:
            resp._cell_scores_cache = {}
        return resp


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
        self._midpoints = [
            (p.earth_min + p.earth_max) / 2.0 for p in registry.parameters
        ]
        dim_indices: dict[str, list[int]] = {d.id: [] for d in registry.dimensions}
        for j, p in enumerate(registry.parameters):
            dim_indices[p.dimension_id].append(j)
        self._dim_indices = dim_indices

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
                ParameterComparison.model_construct(
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

        return RankedAnalogResult.model_construct(
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
        """Evaluate a single Earth site (H3 cell or hotspot) directly without packing an index."""
        (
            _w_vec,
            norm_w_vec,
            _total_weight,
            all_weights_zero,
            eff_spans,
            raw_target,
            eff_target,
            env_deltas,
        ) = self._prepare_target_and_weights(target, weights, mode)

        sp = site.parameters
        earth_row = np.array(
            [float(sp.get(p.id, mid)) for p, mid in zip(self._registry.parameters, self._midpoints)],
            dtype=np.float64,
        )
        sim_row = np.abs(earth_row - eff_target)
        sim_row /= eff_spans
        np.subtract(1.0, sim_row, out=sim_row)
        np.clip(sim_row, 0.0, 1.0, out=sim_row)
        overall_score = 0.0 if all_weights_zero else float(sim_row @ norm_w_vec)

        return self._build_ranked_result(
            site=site,
            target=target,
            earth_row=earth_row,
            sim_row=sim_row,
            overall_score=overall_score,
            raw_target=raw_target,
            eff_target=eff_target,
            env_deltas=env_deltas,
            norm_w_vec=norm_w_vec,
        )

    @staticmethod
    def _score_overall_chunked(
        sub_mat: np.ndarray,
        eff_target: np.ndarray,
        eff_spans: np.ndarray,
        norm_w_vec: np.ndarray,
    ) -> np.ndarray:
        """Compute weighted overall similarity scores using L2-resident row chunks and active columns."""
        n_rows, n_cols = sub_mat.shape
        active_cols = np.flatnonzero(norm_w_vec != 0.0)
        if active_cols.size == 0:
            return np.zeros(n_rows, dtype=np.float64)

        out = np.empty(n_rows, dtype=np.float64)
        chunk_rows = min(_SCORE_CHUNK_ROWS, n_rows)

        if active_cols.size * 2 >= n_cols:
            inv_spans = 1.0 / eff_spans
            buf = np.empty((chunk_rows, n_cols), dtype=np.float64)
            for start in range(0, n_rows, _SCORE_CHUNK_ROWS):
                end = min(start + _SCORE_CHUNK_ROWS, n_rows)
                b = buf[: end - start]
                np.subtract(sub_mat[start:end], eff_target, out=b)
                np.abs(b, out=b)
                b *= inv_spans
                np.subtract(1.0, b, out=b)
                np.clip(b, 0.0, 1.0, out=b)
                np.matmul(b, norm_w_vec, out=out[start:end])
        else:
            w_act = norm_w_vec[active_cols]
            t_act = eff_target[active_cols]
            inv_act = 1.0 / eff_spans[active_cols]
            buf = np.empty((chunk_rows, active_cols.size), dtype=np.float64)
            for start in range(0, n_rows, _SCORE_CHUNK_ROWS):
                end = min(start + _SCORE_CHUNK_ROWS, n_rows)
                b = buf[: end - start]
                np.take(sub_mat[start:end], active_cols, axis=1, out=b)
                b -= t_act
                np.abs(b, out=b)
                b *= inv_act
                np.subtract(1.0, b, out=b)
                np.clip(b, 0.0, 1.0, out=b)
                np.matmul(b, w_act, out=out[start:end])
        return out

    @staticmethod
    def _select_top_k_order(overall_scores: np.ndarray, top_k: int | None) -> np.ndarray:
        """Select indices sorted descending by score, bounded by top_k."""
        active_count = overall_scores.shape[0]
        if top_k == 0 or active_count == 0:
            return np.empty(0, dtype=np.intp)
        neg_scores = -overall_scores
        if top_k is not None and 0 < top_k < active_count:
            nth = float(np.partition(neg_scores, top_k - 1)[top_k - 1])
            candidates = np.flatnonzero(neg_scores <= nth)
            if candidates.size <= max(256, top_k * 8):
                return candidates[np.argsort(neg_scores[candidates], kind="stable")][:top_k]
            return np.argsort(neg_scores, kind="stable")[:top_k]
        return np.argsort(neg_scores, kind="stable")

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
        include_cell_scores: bool = True,
    ) -> EvaluationResponse:
        """Vectorized evaluation over a PrepackedSiteIndex (~85,000 H3 Res 4 cells in <100 ms)."""
        n_total = len(prepacked.sites)
        (
            w_vec,
            norm_w_vec,
            _total_weight,
            all_weights_zero,
            eff_spans,
            raw_target,
            eff_target,
            env_deltas,
        ) = self._prepare_target_and_weights(target, weights, mode)

        dict_template_fn: Callable[[], dict[str, float] | None] | None = None
        if not filters and not exclude_well_known:
            active_indices: np.ndarray | None = None
            active_count = n_total
            sub_mat = prepacked.earth_mat
            filtered_ids: Sequence[str] = prepacked.site_ids
            if include_cell_scores:
                dict_template_fn = prepacked.get_full_dict_template
        elif not filters and exclude_well_known:
            active_indices, sub_mat, filtered_ids, _ = prepacked.get_novel_slice()
            active_count = len(filtered_ids)
            if include_cell_scores:
                dict_template_fn = prepacked.get_novel_dict_template
        else:
            active_indices = prepacked.filter_indices(
                filters=filters,
                exclude_well_known=exclude_well_known,
            )
            active_count = int(active_indices.size)
            sub_mat = prepacked.earth_mat[active_indices]
            site_ids_all = prepacked.site_ids
            filtered_ids = [site_ids_all[i] for i in active_indices.tolist()]

        if active_count == 0:
            return EvaluationResponse.from_scores(
                all_weights_zero=all_weights_zero,
                total_candidates_evaluated=n_total,
                filtered_site_count=0,
                ranked_results=[],
                cell_dimension_scores={},
                include_cell_scores=False,
            )

        need_dim_scores = include_dimension_scores or dimension_id is not None
        cell_dimension_scores: dict[str, dict[str, float | None]] = {}

        if need_dim_scores:
            sim_mat = np.abs(sub_mat - eff_target)
            sim_mat /= eff_spans
            np.subtract(1.0, sim_mat, out=sim_mat)
            np.clip(sim_mat, 0.0, 1.0, out=sim_mat)
            if all_weights_zero:
                overall_scores = np.zeros(active_count, dtype=np.float64)
            else:
                overall_scores = sim_mat @ norm_w_vec

            dim_indices = self._dim_indices
            target_dims = (
                [dimension_id]
                if (dimension_id and dimension_id in dim_indices)
                else list(dim_indices.keys())
            )
            none_col = [None] * active_count
            cols: list[list[float] | list[None]] = []
            for d_id in target_dims:
                idxs = dim_indices[d_id]
                dim_w = w_vec[idxs]
                dim_w_sum = float(dim_w.sum())
                if dim_w_sum <= 0.0:
                    cols.append(none_col)
                else:
                    arr = (sim_mat[:, idxs] @ dim_w) / dim_w_sum
                    cols.append(np.round(arr, 4).tolist())

            dim_keys = tuple(target_dims)
            cell_dimension_scores = {
                sid: dict(zip(dim_keys, row))
                for sid, row in zip(filtered_ids, zip(*cols))
            }
            order = self._select_top_k_order(overall_scores, top_k)
            order_list = order.tolist()
            top_sub = sub_mat
            top_sim = sim_mat
            ranked_results = [
                self._build_ranked_result(
                    site=prepacked.sites[k if active_indices is None else int(active_indices[k])],
                    target=target,
                    earth_row=top_sub[k],
                    sim_row=top_sim[k],
                    overall_score=float(overall_scores[k]),
                    raw_target=raw_target,
                    eff_target=eff_target,
                    env_deltas=env_deltas,
                    norm_w_vec=norm_w_vec,
                )
                for k in order_list
            ]
        else:
            if all_weights_zero:
                overall_scores = np.zeros(active_count, dtype=np.float64)
            else:
                overall_scores = self._score_overall_chunked(
                    sub_mat, eff_target, eff_spans, norm_w_vec
                )
            order = self._select_top_k_order(overall_scores, top_k)
            order_list = order.tolist()
            if order_list:
                top_sub = sub_mat[order]
                top_sim = np.abs(top_sub - eff_target)
                top_sim /= eff_spans
                np.subtract(1.0, top_sim, out=top_sim)
                np.clip(top_sim, 0.0, 1.0, out=top_sim)
            else:
                top_sub = np.empty((0, sub_mat.shape[1]), dtype=np.float64)
                top_sim = top_sub
            ranked_results = [
                self._build_ranked_result(
                    site=prepacked.sites[k if active_indices is None else int(active_indices[k])],
                    target=target,
                    earth_row=top_sub[idx_k],
                    sim_row=top_sim[idx_k],
                    overall_score=float(overall_scores[k]),
                    raw_target=raw_target,
                    eff_target=eff_target,
                    env_deltas=env_deltas,
                    norm_w_vec=norm_w_vec,
                )
                for idx_k, k in enumerate(order_list)
            ]

        return EvaluationResponse.from_scores(
            all_weights_zero=all_weights_zero,
            total_candidates_evaluated=n_total,
            filtered_site_count=active_count,
            ranked_results=ranked_results,
            cell_dimension_scores=cell_dimension_scores,
            site_ids=filtered_ids,
            overall_scores=overall_scores,
            dict_template_fn=dict_template_fn,
            include_cell_scores=include_cell_scores,
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
