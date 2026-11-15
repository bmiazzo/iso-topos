"""Moon & Mars coordinate parameter extractor with bilinear interpolation (FR-3)."""

from __future__ import annotations

from typing import Any

from isotopos.core.models import PlanetaryBody, TargetLocation, TargetPreset
from isotopos.core.registry import ParameterRegistry


class PlanetaryGridInterpolator:
    """Extracts preset vectors or bilinearly interpolates arbitrary (lat, lon) targets."""

    def __init__(
        self,
        registry: ParameterRegistry,
        presets: list[TargetPreset],
        moon_grid: dict[str, Any],
        mars_grid: dict[str, Any],
    ) -> None:
        self._registry = registry
        self._preset_map = {p.id: p for p in presets}
        self._grids = {
            PlanetaryBody.MOON: moon_grid,
            PlanetaryBody.MARS: mars_grid,
        }

    def extract_preset(self, preset_id: str) -> TargetPreset:
        """Return a curated planetary preset without extrapolation."""
        if preset_id not in self._preset_map:
            raise KeyError(f"Unknown preset_id: {preset_id}")
        return self._preset_map[preset_id]

    def extract_coordinate(
        self,
        body: PlanetaryBody,
        lat: float,
        lon: float,
    ) -> TargetLocation:
        """Bilinearly interpolate planetary parameters at an arbitrary (lat, lon)."""
        grid = self._grids[body]
        step = float(grid["step_deg"])
        lats: list[float] = grid["lats"]
        lons: list[float] = grid["lons"]
        values: list[list[dict[str, float]]] = grid["values"]

        clamped_lat = max(-90.0, min(90.0, lat))
        lon_360 = lon % 360.0

        lat_idx_f = (clamped_lat + 90.0) / step
        i0 = min(len(lats) - 2, max(0, int(lat_idx_f)))
        i1 = i0 + 1
        ty = max(0.0, min(1.0, lat_idx_f - i0))

        lon_idx_f = lon_360 / step
        j0 = int(lon_idx_f) % len(lons)
        j1 = (j0 + 1) % len(lons)
        tx = max(0.0, min(1.0, lon_idx_f - int(lon_idx_f)))

        c00 = values[i0][j0]
        c10 = values[i0][j1]
        c01 = values[i1][j0]
        c11 = values[i1][j1]

        interpolated: dict[str, float] = {}
        param_ids = [p.id for p in self._registry.parameters]
        for pid in param_ids:
            v0 = (1.0 - tx) * c00[pid] + tx * c10[pid]
            v1 = (1.0 - tx) * c01[pid] + tx * c11[pid]
            interpolated[pid] = round((1.0 - ty) * v0 + ty * v1, 4)

        return TargetLocation(
            name=f"{body.value.title()} ({clamped_lat:.2f}°, {lon_360:.2f}°E)",
            body=body,
            lat=round(clamped_lat, 4),
            lon=round(lon_360, 4),
            parameters=interpolated,
            is_extrapolated=True,
            extrapolated_parameters=param_ids,
            notes=f"Bilinearly interpolated from {step:.1f}° {body.value.title()} global spatial grid (FR-3).",
        )

    def get_grid_parameter_slice(self, body: PlanetaryBody, param_id: str) -> dict[str, Any]:
        """Return lightweight 2D grid matrix for a single planetary parameter (for /planetary overlay)."""
        grid = self._grids[body]
        values: list[list[float]] = [
            [round(float(cell.get(param_id, 0.0)), 4) for cell in row]
            for row in grid["values"]
        ]
        return {
            "body": body.value,
            "parameter_id": param_id,
            "step_deg": float(grid["step_deg"]),
            "lats": grid["lats"],
            "lons": grid["lons"],
            "values": values,
        }
