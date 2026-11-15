# Lunar Polar Shadows in Optical WMTS & CesiumJS 2D/3D Zoom Clamps

- **Date:** 2026-11-15
- **Area / Tags:** `frontend`, `cesiumjs`, `moon`, `wmts`, `zoom`, `poles`

## What Surprised Us
1. **`LRO_WAC_Mosaic_Global_303ppd_v02` has ~86% black pixels in polar tiles:** Even though NASA Moon Trek serves `LRO_WAC_Mosaic` cleanly in `EPSG:4326` (`2x1` level 0, `-90°..+90°`), optical imaging of permanently shadowed polar craters produces near-black streaks (`mean=9.4`, `zero_frac=0.86` on `5/31/0.jpg`) that look like projection distortion around `-90°` and `+90°`. Meanwhile, **`LRO_LOLA_Shade_Global_128ppd_v04`** and **`LRO_LOLA_ClrShade_Global_128ppd_v04`** (laser altimetry) have `zero_val=0.000` and `zero_a=0.000` across both poles.
2. **Clamping target height BEFORE branching zoom direction inverts `+`/`-`:** If `height < minDist` (e.g., after wheel inertia) and a `+` handler computes `targetHeight = max(minDist, height / factor)` and then branches on `delta = height - targetHeight < 0` to call `zoomOut(-delta)`, clicking `+` zooms **out**.
3. **CesiumJS `SCENE2D` keeps `camera.positionCartographic.height` constant:** Zooming in 2D changes `camera.frustum.left/right/top/bottom`, not `positionCartographic.height`, and Cesium `zoom2D` scales along whichever span (`left/right` vs `top/bottom`) is larger. Furthermore, Cesium's default `camera.percentageChanged = 0.5` suppresses `camera.changed` callbacks during incremental wheel zooming.

## Why It Matters
Optical global mosaics alone make lunar south-pole exploration sites (`Shackleton Rim` at `-89.9°`, `Malapert` at `-86.0°`) hard to distinguish inside black shadow streaks, and naive clamp-then-delta zoom math or `SCENE3D`-only `cameraHeightToApproxZoom` breaks zooming and LOD/outline sync.

## Rule of Thumb / What To Do Instead
- Default Moon topography/navigation views to shadow-free **`LRO_LOLA_Shade_Global_128ppd_v04`** (or blend LRO WAC semi-transparently over LOLA shaded relief) so polar craters stay sharp.
- Gate zoom-in vs. zoom-out strictly on `factor > 1` / `factor < 1` before clamping deltas, measure `SCENE2D` zoom via `Math.max(|right-left|, |top-bottom|)`, lower `camera.percentageChanged` (e.g., `0.02`), and pass explicit nadir orientation for `SCENE3D` near-pole flights (`|lat| > 89°`).

## References
- `src/isotopos/static/js/components/cesium_helpers.js`
- `src/isotopos/static/js/planetary_page.js`
- `decisions/DECISIONS.md` (`DEC-016`)
