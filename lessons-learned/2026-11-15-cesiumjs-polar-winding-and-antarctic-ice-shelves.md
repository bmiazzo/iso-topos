# CesiumJS Polar-Encircling Polygon Winding & Natural Earth Ice Shelf Exclusion

- **Date:** 2026-11-15
- **Area / Tags:** `etl`, `h3`, `cesiumjs`, `antarctica`, `coordinates`

## What Surprised Us
1. **Inward-Facing Triangulation on Pole-Encircling Polygons in CesiumJS:** Even though `Cesium.PolygonGeometry.createGeometry` returns a non-null mesh for the unsplit `-90°` South Pole hexagon (`84f2939ffffffff`), its `305.77°`-wide ring crossing `±180°` caused Cesium's 2D winding check to flip all 8 triangles inward (`outward: 0, inward: 8`) while every other polar cell had outward normals.
2. **Natural Earth `ne_50m_land.geojson` Excludes Antarctic Ice Shelves:** Ross, Filchner-Ronne, Amery, and Larsen ice shelves are omitted from `ne_50m_land.geojson` (and `ne_50m_admin_0_countries.geojson`), leaving 593 H3 Res 4 ocean cutouts inside Antarctica on Blue Marble / MODIS imagery. They live in a separate Natural Earth layer (`ne_50m_antarctic_ice_shelves_polys.geojson`).
3. **Single-Vertex Overlap Miss & `PolylineGeometry` Appearance Constraint:** `h3.polygon_to_cells_experimental(..., contain="overlap")` skipped 1 coastal vertex cell (`840ea69ffffffff` at `62.82°N, -91.35°E`), and in CesiumJS `PolylineGeometry` cannot share a `Primitive` batch with `PolygonOutlineGeometry` because it requires `PolylineColorAppearance` and `Cartesian3.fromDegreesArrayHeights`.

## Why It Matters
- Inverted triangles and `>90°` longitude spans break polar rendering in 3D/2D Cesium modes.
- Missing Antarctic ice shelves leave large visible gaps across the Antarctic continent.
- Mixing `PolygonOutlineGeometry` and `PolylineGeometry` in one Cesium `Primitive` fails appearance validation.

## Rule of Thumb / What To Do Instead
- Fan any pole-encircling H3 ring into `<= 90°`-longitude wedges meeting at `±90.0°` (splitting `±180°` crossings at `±180.0°`) via `fan_polar_ring()` so all GeoJSON rings satisfy `lon_span <= 90°` and produce outward Cesium triangles.
- Include `ne_50m_antarctic_ice_shelves_polys.geojson` alongside `ne_50m_land.geojson` and always add `h3.latlng_to_cell(lat, lon, res)` for polygon boundary vertices.
- Batch `MultiPolygon` outer-perimeter outlines separately with `PolylineGeometry` (`PolylineColorAppearance`) and omit internal `|lat| == 90°` / `|lon| == 180°` split segments.

## References
- `src/isotopos/etl/h3_geometry.py`
- `src/isotopos/static/js/components/globe_map.js`
- `src/isotopos/static/js/planetary_page.js`
- `DEC-015` in `decisions/DECISIONS.md`
