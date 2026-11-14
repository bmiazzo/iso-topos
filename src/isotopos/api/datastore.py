"""In-memory spatial index and pre-packed NumPy matrix container (DR-2, DEC-005, ER-4)."""

from __future__ import annotations

import functools
import json
from pathlib import Path

from isotopos.core.models import EarthSite, PlanetaryBody, TargetPreset
from isotopos.core.registry import DEFAULT_REGISTRY, ParameterRegistry
from isotopos.etl.catalog_data import EARTH_HOTSPOTS, PLANETARY_PRESETS
from isotopos.etl.interpolator import PlanetaryGridInterpolator
from isotopos.etl.spatial_builder import build_earth_h3_grid, build_planetary_grid
from isotopos.scoring.engine import AnalogScoringEngine, PrepackedSiteIndex


class DataStore:
    """In-memory pre-loaded spatial index and pre-packed NumPy matrix container."""

    def __init__(
        self,
        data_dir: Path | None = None,
        registry: ParameterRegistry = DEFAULT_REGISTRY,
        fallback_max_cells: int = 500,
        fallback_step_deg: float = 10.0,
    ) -> None:
        self.registry = registry
        root = Path(__file__).resolve().parents[3]
        processed = data_dir or (root / "data" / "processed")

        if (processed / "earth_h3_sites.json").exists():
            raw_sites = json.loads((processed / "earth_h3_sites.json").read_text(encoding="utf-8"))
            self.h3_sites = [EarthSite.model_construct(**s) for s in raw_sites]
            self.earth_geojson = json.loads(
                (processed / "earth_h3_grid.geojson").read_text(encoding="utf-8")
            )
            raw_hotspots = json.loads((processed / "earth_hotspots.json").read_text(encoding="utf-8"))
            self.hotspots = [EarthSite(**h) for h in raw_hotspots]
            raw_presets = json.loads(
                (processed / "planetary_presets.json").read_text(encoding="utf-8")
            )
            self.presets = [TargetPreset(**p) for p in raw_presets]
            moon_grid = json.loads((processed / "moon_grid.json").read_text(encoding="utf-8"))
            mars_grid = json.loads((processed / "mars_grid.json").read_text(encoding="utf-8"))
        else:
            self.h3_sites, self.earth_geojson = build_earth_h3_grid(max_cells=fallback_max_cells)
            self.hotspots = list(EARTH_HOTSPOTS)
            self.presets = list(PLANETARY_PRESETS)
            moon_grid = build_planetary_grid(PlanetaryBody.MOON, step_deg=fallback_step_deg)
            mars_grid = build_planetary_grid(PlanetaryBody.MARS, step_deg=fallback_step_deg)

        self.h3_prepacked = PrepackedSiteIndex.from_sites(self.h3_sites, registry)
        self.hotspot_prepacked = PrepackedSiteIndex.from_sites(self.hotspots, registry)

        self.interpolator = PlanetaryGridInterpolator(
            registry=registry,
            presets=self.presets,
            moon_grid=moon_grid,
            mars_grid=mars_grid,
        )
        self.engine = AnalogScoringEngine(registry)


@functools.lru_cache(maxsize=1)
def get_default_datastore() -> DataStore:
    """Return a singleton DataStore loaded from the default `data/processed` directory."""
    return DataStore()
