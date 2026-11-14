"""Pre-packed contiguous NumPy site matrix and physical filter index (DEC-005, NFR-1)."""

from __future__ import annotations

import numpy as np

from isotopos.core.models import EarthSite, PhysicalFilter
from isotopos.core.registry import ParameterRegistry


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
        """Return {site_id: rounded_value} mapping for a single registered parameter."""
        col = self.param_col_index[parameter_id]
        vals = np.round(self.earth_mat[:, col], 4).tolist()
        return dict(zip(self.site_ids, vals))

    def filter_indices(
        self,
        filters: list[PhysicalFilter] | None = None,
        exclude_well_known: bool = False,
    ) -> np.ndarray:
        """Return 1D array of site row indices passing novelty and physical range filters."""
        n_total = len(self.sites)
        keep = np.ones(n_total, dtype=bool)
        if exclude_well_known:
            keep &= ~self.well_known_mask

        for flt in filters or []:
            col = self.param_col_index.get(flt.parameter_id)
            if col is None:
                keep[:] = False
                break
            col_vals = self.earth_mat[:, col]
            if flt.min_value is not None:
                keep &= col_vals >= flt.min_value
            if flt.max_value is not None:
                keep &= col_vals <= flt.max_value

        return np.flatnonzero(keep)
