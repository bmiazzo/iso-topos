# CesiumJS Non-WGS84 `Viewer` Ellipsoid/Projection Mismatch & Polar Overlay Starbursts

- **Date:** 2026-11-15
- **Area / Tags:** `frontend`, `cesiumjs`, `planetary-data`, `coordinates`, `zoom`

## What Surprised Us
1. Passing `globe: new Cesium.Globe(targetEllipsoid)` and `terrainProvider: new Cesium.EllipsoidTerrainProvider({ ellipsoid: targetEllipsoid })` to `new Cesium.Viewer(...)` was **not enough** to configure Cesium for Moon (`R = 1,737,400 m`) or Mars (`R = 3,396,190 m`). Without also passing `ellipsoid: targetEllipsoid` and `mapProjection: new Cesium.GeographicProjection(targetEllipsoid)` in `Viewer` options, `scene.ellipsoid` and `scene.mapProjection.ellipsoid` silently defaulted to `WGS84` (`6,378,137 m`).
   As a result, `camera.positionCartographic.height` on Moon reported **`-2,018,115 m`** (negative!) even when hovering 2.6M m above the lunar surface. On the very first mouse-wheel event, `ScreenSpaceCameraController` saw `height < minimumZoomDistance`, called `camera.zoomIn(-2038965)` (throwing the camera out to ~6,378 km radius), and then locked `zoomIn(0)` permanently.
2. On `/planetary`, `moon_grid.json` and `mars_grid.json` contain non-uniform values across the 144 longitudes at `lat = -90.0°` (`elevation_m` spans `-2009 m..+1666 m` on Moon) and `141/144` exact `0.0`s at Moon `lat = +90.0°`. When rasterized directly to equirectangular `SingleTileImageryProvider` overlays (or shaded fallback layers), varying longitude values along the single pole singularity create bright/dark **pinwheel starburst spokes** radiating from `±90°` on a 3D sphere.

## Why It Matters
- **Broken zooming & horizon occlusion on non-Earth globes:** Any camera distance check, `ScreenSpaceCameraController` zoom step, 2D frustum scaling, or `scene.occluder` billboard culling breaks silently if `scene.ellipsoid` / `mapProjection.ellipsoid` differs from `globe.ellipsoid`.
- **Polar rendering & overlay artifacts:** Un-averaged `±90°` pole rows corrupt elevation/temperature overlays right over polar targets like Shackleton Crater (`-89.9°`), and high-zoom NASA Trek layers go up to `TileMatrix 8` (Moon) and `7` (Mars), whereas `maximumLevel: 6` capped resolution unnecessarily near the pole.

## Rule of Thumb / What To Do Instead
1. Whenever constructing a non-WGS84 `Cesium.Viewer`, explicitly pass **all four**: `ellipsoid: targetEllipsoid`, `mapProjection: new Cesium.GeographicProjection(targetEllipsoid)`, `globe: new Cesium.Globe(targetEllipsoid)`, and `terrainProvider: new Cesium.EllipsoidTerrainProvider({ ellipsoid: targetEllipsoid })`, plus scaled `ctrl.minimumZoomDistance` / `maximumZoomDistance` and explicit `+`/`−`/`Reset` controls via `zoomViewerByFactor` supporting both `SCENE3D` and `SCENE2D` (`frustum.right - frustum.left`). Cancel active `camera.flyTo()` flights on `LEFT_DOWN`, `RIGHT_DOWN`, and `WHEEL`.
2. Before rasterizing equirectangular global slices onto a sphere (`renderSliceToEquirectangularDataUrl`), normalize both `lat = -90°` and `lat = +90°` pole rows (`buildPoleNormalizedRows`) to a single azimuthally uniform ring mean (falling back to the `nLat - 2` ring mean when `>= 80%` of `+90°` entries are `0.0` while `nLat - 2` is non-zero), use subtle natural albedo ramps instead of `viridis`/`magma` for shaded terrain fallback, and match `TileMatrixLabels`/`maximumLevel` to NASA Trek WMTS capabilities (`8` Moon, `7` Mars).

## References
- `src/isotopos/static/js/components/cesium_helpers.js` (`createCesiumViewer`, `zoomViewerByFactor`, `flyToLatLon`)
- `src/isotopos/static/js/planetary_page.js` (`PLANETARY_TILES`, `buildPoleNormalizedRows`, `renderSliceToEquirectangularDataUrl`)
- `src/isotopos/static/js/components/globe_map.js`, `src/isotopos/static/app.js`, `src/isotopos/static/index.html`, `src/isotopos/static/planetary.html`
- `DEC-014`, `DEC-015`
