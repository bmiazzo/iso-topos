# Wikimedia API User-Agent Requirement & MapLibre Raw-Layer Masking

- **Date:** 2026-11-15
- **Area / Tags:** `frontend`, `maplibre`, `wikimedia`, `api`

## What Surprised Us
1. **Wikimedia Commons / Wikipedia REST APIs return HTTP `403 Forbidden`** to standard Python HTTP clients unless `User-Agent` follows Wikimedia's bot/tool format (`AppName/Version (url; contact)`). Browser `fetch()` requests to Wikipedia GeoSearch require `&origin=*` for CORS.
2. **In the Earth 3D MapLibre frontend, `raw:<param_id>` physical parameter layers were previously gated inside `if (id in cell_scores)`**, which silently hid physical datasets (like magnetic anomaly or permafrost) in every H3 cell excluded by mission filters or `Beyond Well-Known Sites`.
3. **MapLibre `image` sources in `globe` projection expect Web Mercator `y` spacing (`[-85.0511°, +85.0511°]`)**, so drawing equirectangular `(lat, lon)` grid rows linearly onto an offscreen canvas shifts mid-latitude Moon/Mars features vertically unless canvas row `y` is inverted through the Mercator latitude formula (`atan(exp(mercY))`).

## Why It Matters
- Hiding raw Earth physics inside excluded regions misleads scientists into thinking Antarctica or filtered deserts have no data rather than simply being excluded from analog ranking.
- Unwarped equirectangular canvas overlays misalign planetary crater and magnetic anomalies on the `/planetary` 3D Moon/Mars globe.

## Rule of Thumb / What To Do Instead
- Always send an explicit `App/Version (url; contact)` `User-Agent` when calling Wikimedia APIs from backend scripts, and include `&origin=*` for client-side Wikipedia GeoSearch requests.
- Decouple `raw:` layer lookup from `cell_scores` in `globe_map.js`: only similarity score/dimension layers should be filtered by `minScoreFilter` or dimmed by `excludeWellKnown`.
- When baking equirectangular 2D scientific grids (`[-90..90]`) into a MapLibre `image` source canvas for `globe` projection, sample each canvas pixel via exact Web Mercator inverse latitude (`mercY = pi * (1 - 2 * (py + 0.5) / H)`).

## References
- [`globe_map.js`](../src/isotopos/static/js/components/globe_map.js)
- [`planetary_page.js`](../src/isotopos/static/js/planetary_page.js)
- [`hotspot_enrichment.py`](../src/isotopos/etl/sources/hotspot_enrichment.py)
