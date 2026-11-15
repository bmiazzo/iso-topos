"""Offline ETL script to generate pre-processed spatial indices from real open datasets (DR-1, DR-2, NFR-3)."""

from __future__ import annotations

import argparse
import gc
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from isotopos.core.models import PlanetaryBody  # noqa: E402
from isotopos.etl.catalog_data import PLANETARY_PRESETS  # noqa: E402
from isotopos.etl.sources.earth_datasets import EarthOpenDatasets  # noqa: E402
from isotopos.etl.spatial_builder import (  # noqa: E402
    build_earth_h3_grid,
    build_enriched_hotspots,
    build_planetary_grid,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build processed spatial indices into data/processed/.")
    parser.add_argument("--raw-dir", type=Path, default=None, help="Override data/raw directory.")
    parser.add_argument(
        "--allow-fallback",
        action="store_true",
        help="Allow synthetic fallback if real open datasets are missing in raw_dir.",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    raw_dir = args.raw_dir or (root / "data" / "raw")
    out_dir = root / "data" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    require_real = not args.allow_fallback

    print(f"Loading open Earth datasets from {raw_dir} ...")
    earth_ds = EarthOpenDatasets.from_raw_dir(raw_dir) if require_real else None

    print("Aggregating Earth H3 Res 4 land grid ...")
    sites, geojson = build_earth_h3_grid(raw_dir=raw_dir, require_real=require_real, earth_ds=earth_ds)
    hotspots = build_enriched_hotspots(raw_dir=raw_dir, require_real=require_real, earth_ds=earth_ds)
    del earth_ds
    gc.collect()

    n_sites = len(sites)
    wk_h3 = sum(1 for s in sites if s.is_well_known)
    interp_cells = sum(1 for s in sites if s.interpolated_parameters)

    with (out_dir / "earth_h3_sites.json").open("w", encoding="utf-8") as fp:
        json.dump([s.model_dump() for s in sites], fp, separators=(",", ":"))
    del sites
    gc.collect()

    with (out_dir / "earth_h3_grid.geojson").open("w", encoding="utf-8") as fp:
        json.dump(geojson, fp, separators=(",", ":"))
    del geojson
    gc.collect()

    n_hotspots = len(hotspots)
    wk_hs = sum(1 for h in hotspots if h.is_well_known)
    with (out_dir / "earth_hotspots.json").open("w", encoding="utf-8") as fp:
        json.dump([h.model_dump() for h in hotspots], fp, indent=2)
    del hotspots
    gc.collect()

    with (out_dir / "planetary_presets.json").open("w", encoding="utf-8") as fp:
        json.dump([p.model_dump() for p in PLANETARY_PRESETS], fp, indent=2)

    print("Building Moon 2.5-deg NASA PDS / SH grid ...")
    moon_grid = build_planetary_grid(PlanetaryBody.MOON, step_deg=2.5, raw_dir=raw_dir, require_real=require_real)
    with (out_dir / "moon_grid.json").open("w", encoding="utf-8") as fp:
        json.dump(moon_grid, fp, separators=(",", ":"))
    del moon_grid
    gc.collect()

    print("Building Mars 2.5-deg NASA PDS / SH grid ...")
    mars_grid = build_planetary_grid(PlanetaryBody.MARS, step_deg=2.5, raw_dir=raw_dir, require_real=require_real)
    with (out_dir / "mars_grid.json").open("w", encoding="utf-8") as fp:
        json.dump(mars_grid, fp, separators=(",", ":"))
    del mars_grid
    gc.collect()

    print(
        f"Built spatial index in {out_dir}: "
        f"{n_sites} H3 Res 4 cells ({wk_h3} well-known, {interp_cells} with interpolated track gaps), "
        f"{n_hotspots} hotspots ({wk_hs} well-known), {len(PLANETARY_PRESETS)} Moon/Mars presets."
    )


if __name__ == "__main__":
    main()
