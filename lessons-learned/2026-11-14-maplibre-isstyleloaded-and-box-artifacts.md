# MapLibre `isStyleLoaded()` Blocking UI Updates & Axis-Aligned Grid Artifacts

- **Date:** 2026-11-14
- **Area / Tags:** `frontend`, `maplibre`, `etl`, `spatial-synthesis`

## What Surprised Us
1. **`map.isStyleLoaded()` returns `false` while external raster tiles stream:** In MapLibre GL JS v5, `isStyleLoaded()` checks whether all sources (including remote NASA GIBS raster tiles and re-tiled GeoJSON) have zero pending tile loads. Guarding `updateEarthMapLayers()` with `if (!state.map.isStyleLoaded()) return;` silently dropped menu changes (palette, layer variable, opacity, spotlight threshold, hotspot toggle) whenever tiles were loading or after switching basemaps.
2. **Simultaneous hotspot & polygon `click` listeners:** Registering separate `map.on("click", "earth-hotspots-circle", ...)` and `map.on("click", "earth-h3-fill", ...)` handlers caused both to fire on a single click—the async `/api/v1/site/{id}` H3 lookup resolved after the synchronous hotspot update and overwrote it.
3. **Axis-aligned `lat/lon` conditions create sharp rectangular clusters:** Writing `if lat_a <= lat <= lat_b and lon_a <= lon <= lon_b` in `_synthesize_earth_cell_parameters` produced straight-edged rectangular blocks of near-identical evaluations on the H3 globe.

## Why It Matters
- Users see menus and toggles appear completely broken ("no effect"), clicks on hotspots inspect the wrong site, and rectangular clusters distort scientific interpretation of spatial analogs.

## Rule of Thumb / What To Do Instead
- Track an explicit `mapReady` flag in `map.on("load")` and check `map.getLayer(...)` instead of `map.isStyleLoaded()` before updating paint/source properties; use `promoteId` + `setFeatureState` for fast per-cell styling without re-sending large GeoJSON payloads.
- Handle map clicks and hover tooltips with a single listener using `map.queryRenderedFeatures(e.point, { layers: ["earth-hotspots-circle", "earth-h3-fill"] })` so top overlay markers take priority.
- Model spatial provinces using `cos(lat)`-corrected geodesic Gaussian RBFs and smooth sigmoids—never hard `lat/lon` bounding boxes.

## References
- `src/isotopos/static/app.js`
- `src/isotopos/etl/spatial_builder.py`
- `DEC-006` in `decisions/DECISIONS.md`
