"""Offline ETL script to generate lightweight pre-processed spatial indices (DR-2, NFR-3)."""

from __future__ import annotations

import json
from pathlib import Path

from isotopos.core.models import PlanetaryBody
from isotopos.etl.catalog_data import EARTH_HOTSPOTS, PLANETARY_PRESETS
from isotopos.etl.spatial_builder import build_earth_h3_grid, build_planetary_grid


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    out_dir = root / "data" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)

    sites, geojson = build_earth_h3_grid()

    (out_dir / "earth_h3_sites.json").write_text(
        json.dumps([s.model_dump() for s in sites], separators=(",", ":")),
        encoding="utf-8",
    )
    (out_dir / "earth_h3_grid.geojson").write_text(
        json.dumps(geojson, separators=(",", ":")),
        encoding="utf-8",
    )
    (out_dir / "earth_hotspots.json").write_text(
        json.dumps([h.model_dump() for h in EARTH_HOTSPOTS], indent=2),
        encoding="utf-8",
    )
    (out_dir / "planetary_presets.json").write_text(
        json.dumps([p.model_dump() for p in PLANETARY_PRESETS], indent=2),
        encoding="utf-8",
    )
    (out_dir / "moon_grid.json").write_text(
        json.dumps(build_planetary_grid(PlanetaryBody.MOON, step_deg=5.0), separators=(",", ":")),
        encoding="utf-8",
    )
    (out_dir / "mars_grid.json").write_text(
        json.dumps(build_planetary_grid(PlanetaryBody.MARS, step_deg=5.0), separators=(",", ":")),
        encoding="utf-8",
    )

    print(
        f"Built spatial index in {out_dir}: "
        f"{len(sites)} Uniform H3 Res 4 cells, {len(EARTH_HOTSPOTS)} hotspots, "
        f"{len(PLANETARY_PRESETS)} Moon/Mars presets."
    )


if __name__ == "__main__":
    main()
