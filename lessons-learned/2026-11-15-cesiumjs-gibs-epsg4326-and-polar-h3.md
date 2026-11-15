# CesiumJS NASA GIBS `EPSG:4326` TileMatrix Offset, CDN Workers & Polar-Encircling H3 Cells

- **Date:** 2026-11-15
- **Area / Tags:** `frontend`, `cesiumjs`, `etl`, `h3`, `gibs`, `coordinates`

## What Surprised Us
1. **NASA GIBS `EPSG:4326` `TileMatrix 0..2` Non-Standard Grid:** In NASA GIBS `epsg4326` WMTS (`500m` / `250m` TileMatrixSets), `TileMatrix 0`, `1`, and `2` have dimensions `2×1`, `3×2`, and `5×3` (based on a `288°` origin span) rather than standard `2×1, 4×2, 8×4` powers of two. Using `new Cesium.GeographicTilingScheme()` directly at zoom `0` causes every tile from level 1 onward to shift/stretch by tens of degrees. However, starting at `TileMatrix 3` (`10×5`, each `36°×36°`), every subsequent level (`20×10`, `40×20`, ...) divides `[-180..180] × [-90..90]` by exact powers of two.
2. **CDN Cross-Origin WebWorker `SecurityError`:** Loading CesiumJS from `unpkg.com` (`CESIUM_BASE_URL` cross-origin) causes `Cesium.Primitive` with default `asynchronous: true` to throw `SecurityError` when `TaskProcessor` tries to instantiate `new Worker("https://unpkg.com/.../cesiumWorkerBootstrapper.js")`.
3. **South Pole-Encircling H3 Cell (`-90°`):** Once the `±84.5°` clamp was removed, the H3 cell straddling `-90°` has boundary longitudes spanning `-180°..+180°` even after `[0, 360]` unwrapping (because it encircles the pole rather than crossing the antimeridian), so `safe_hex_geometry()` dropped it until an explicit `all(abs(lt) > 85.0)` polar-cap branch was added.

## Why It Matters
- Misaligned GIBS tile matrices shift continents off the H3 hexagons.
- Cross-origin worker failures silently prevent all 88k+ H3 hexagons from rendering on CDN-hosted CesiumJS.
- Dropping polar-encircling cells leaves a pentagon hole at `-90°`.

## Rule of Thumb / What To Do Instead
- For NASA GIBS `EPSG:4326` `500m`/`250m` WMTS in CesiumJS, configure `GeographicTilingScheme({ numberOfLevelZeroTilesX: 10, numberOfLevelZeroTilesY: 5 })` with `tileMatrixLabels: ["3", "4", "5", ...]` and `tileWidth: 512, tileHeight: 512`.
- Use `asynchronous: false` in chunked `Cesium.Primitive` batches (~4,500 instances per frame via `setTimeout(0)`) when serving CesiumJS from a cross-origin CDN without a local worker proxy.
- In `h3_geometry.py`, preserve cells whose boundary vertices satisfy `all(abs(lt) > 85.0)` as valid polar-cap `Polygon` rings.

## References
- `src/isotopos/static/js/components/globe_map.js`
- `src/isotopos/etl/h3_geometry.py`
- `DEC-014` in `decisions/DECISIONS.md`
