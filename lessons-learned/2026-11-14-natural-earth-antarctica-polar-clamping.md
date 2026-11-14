# Natural Earth Antarctica Polygon Clamping vs. Vertex Filtering for H3

- **Date:** 2026-11-14
- **Area / Tags:** `etl`, `h3`, `natural-earth`, `antarctica`, `coordinates`

## What Surprised Us
In Natural Earth (`ne_50m_land.geojson`, Feature 1378), the Antarctica polygon is closed along the South Pole via 257 vertices at `lat = -90.0°` running from `lon = +180.0°` to `-180.0°`. When preparing polygon rings for H3 within Web Mercator's safe latitude band (`|lat| <= 84.5°`), filtering out vertices with `abs(lat) > 84.5` deleted the entire southern closing edge of the continent, causing the polygon ring to snap directly across the hemisphere and omitting ~40% of East Antarctica (`3,687` H3 Res 4 cells instead of `6,200`).

## Why It Matters
Dropping out-of-range polar vertices instead of clamping them creates huge missing wedges across East Antarctica (including Dome A and the polar plateau), which are primary terrestrial analogs for Lunar South Pole cold traps and Mars polar caps.

## Rule of Thumb / What To Do Instead
- **Clamp, do not drop**, polygon ring latitudes (`max(-84.5, min(84.5, lat))`) before passing Natural Earth coastline rings into `h3.LatLngPoly` / `h3.polygon_to_cells_experimental`.
- After extracting H3 cells, filter cell centers with `abs(h3.cell_to_latlng(cid)[0]) <= 84.5` and split any antimeridian-crossing hexagons (`max(lon) - min(lon) > 180°`) into valid `MultiPolygon` halves along `±180.0°`.

## References
- `src/isotopos/etl/spatial_builder.py` (`_load_land_h3_cells`, `_safe_hex_geometry`)
- `tests/unit/test_etl_and_interpolation.py`
- `DEC-005` in `decisions/DECISIONS.md`
