"""In-memory spatial index and pre-packed NumPy matrix container (DR-2, DEC-005, ER-4)."""

from __future__ import annotations

import functools
import gzip
import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from isotopos.core.models import EarthSite, PlanetaryBody, TargetPreset
from isotopos.core.registry import DEFAULT_REGISTRY, ParameterRegistry
from isotopos.etl.catalog_data import EARTH_HOTSPOTS, PLANETARY_PRESETS
from isotopos.etl.interpolator import PlanetaryGridInterpolator
from isotopos.etl.sources.hotspot_enrichment import enrich_hotspots_from_datasets
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

        self._earth_geojson_raw_bytes: bytes | None = None
        if (processed / "earth_h3_sites.json").exists():
            raw_sites = json.loads((processed / "earth_h3_sites.json").read_text(encoding="utf-8"))
            self.h3_sites = [EarthSite.model_construct(**s) for s in raw_sites]
            raw_geojson_bytes = (processed / "earth_h3_grid.geojson").read_bytes()
            self._earth_geojson_raw_bytes = raw_geojson_bytes
            self.earth_geojson = json.loads(raw_geojson_bytes)
            raw_hotspots = json.loads((processed / "earth_hotspots.json").read_text(encoding="utf-8"))
            loaded_hotspots = [EarthSite(**h) for h in raw_hotspots]
            # Backfill country/photo metadata cleanly if processed hotspots predate enrichment.
            if any(not h.country or not h.photo_url for h in loaded_hotspots):
                self.hotspots = enrich_hotspots_from_datasets(loaded_hotspots)
            else:
                self.hotspots = loaded_hotspots
            raw_presets = json.loads(
                (processed / "planetary_presets.json").read_text(encoding="utf-8")
            )
            self.presets = [TargetPreset(**p) for p in raw_presets]
            moon_grid = json.loads((processed / "moon_grid.json").read_text(encoding="utf-8"))
            mars_grid = json.loads((processed / "mars_grid.json").read_text(encoding="utf-8"))
        else:
            self.h3_sites, self.earth_geojson = build_earth_h3_grid(max_cells=fallback_max_cells)
            self.hotspots = enrich_hotspots_from_datasets(list(EARTH_HOTSPOTS))
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
        self._json_payload_cache: dict[str, tuple[bytes, bytes]] = {}
        self._json_etag_cache: dict[str, str] = {}

    def get_cached_json_payload(
        self,
        key: str,
        builder: Callable[[], Any],
    ) -> tuple[bytes, bytes]:
        """Serialize JSON once and cache both plain and gzip-compressed UTF-8 bytes."""
        cached = self._json_payload_cache.get(key)
        if cached is not None:
            return cached
        if key == "earth_grid" and self._earth_geojson_raw_bytes is not None:
            raw_bytes = self._earth_geojson_raw_bytes
        else:
            raw_bytes = json.dumps(builder(), separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        gz_bytes = gzip.compress(raw_bytes, compresslevel=5)
        entry = (raw_bytes, gz_bytes)
        self._json_payload_cache[key] = entry
        self._json_etag_cache[key] = f'"{hashlib.sha256(raw_bytes).hexdigest()[:16]}"'
        return entry

    def get_cached_json_with_etag(
        self,
        key: str,
        builder: Callable[[], Any],
    ) -> tuple[bytes, bytes, str]:
        """Return cached (raw_bytes, gz_bytes, etag) for conditional HTTP responses."""
        raw_bytes, gz_bytes = self.get_cached_json_payload(key, builder)
        return raw_bytes, gz_bytes, self._json_etag_cache[key]


@functools.lru_cache(maxsize=1)
def get_default_datastore() -> DataStore:
    """Return a singleton DataStore loaded from the default `data/processed` directory."""
    return DataStore()
