# H3 Polar Cells & Web Mercator ±85.05° Distortion in MapLibre Globe

- **Date:** 2026-11-14
- **Area / Tags:** `etl`, `h3`, `coordinates`, `frontend`, `maplibre-globe`

## What Surprised Us
Even when MapLibre GL JS v5 is rendering in `globe` projection, its internal GeoJSON tiler (`geojson-vt`) and `epsg:3857` raster tile sources operate in Web Mercator space, which clips at `±85.051129°` latitude. Additionally, H3 hexagons sitting directly on the South Pole (`-90°`) produce GeoJSON rings spanning `> 270°` of longitude, causing severe triangular/ribbon distortions around the poles.

## Why It Matters
93 Antarctic H3 cells had vertices beyond `-85.05°` and 8 polar cells had wide longitude spans, creating visual artifacts at the poles on the 3D globe.

## Rule of Thumb / What To Do Instead
- Keep all H3 cell centers within `|lat| <= 84.5°` and clamp polygon vertices to `[-84.95°, 84.95°]` when targeting MapLibre GL JS `globe` projection.
- Drop or split any polygon whose raw longitude span exceeds `90°` before writing GeoJSON.
- Enforce these bounds in automated ETL unit tests.

## References
- `src/isotopos/etl/spatial_builder.py` (`_is_earth_land`, `_safe_hex_polygon`)
- `tests/unit/test_etl_and_interpolation.py`
