# Forced `gc.collect()` Pauses, Eager `dict(zip)` Scoring Allocations & `MultiPolygon` Antimeridian Coordinate Bugs

- **Date:** 2026-11-15
- **Area / Tags:** `scoring`, `performance`, `api`, `frontend`, `geojson`

## What Surprised Us
1. **Unconditional `gc.collect()` on a 1.5M-object heap:** Calling `gc.collect()` inside `PrepackedSiteIndex.from_sites`—including inside `evaluate_single_site()` and tiny unit tests—paused execution for ~1.1 s whenever `DataStore` had loaded the ~87,815 `EarthSite` objects and GeoJSON dicts into long-lived memory.
2. **Python `dict(zip(...))` dominated NumPy scoring:** Across ~87,815 H3 cells, vectorized distance scoring took ~15 ms, whereas building and discarding an 87,815-entry `dict[str, float]` (`EvaluationResponse.cell_scores`) plus Pydantic model validation for 255+ breakdown items added ~52–86 ms—pushing total `evaluate_prepacked` close to or past the 100 ms `NFR-1` budget.
3. **`MultiPolygon` coordinate ring bug & `O(N)` grid lookups:** In the frontend, `resolveSiteCoords()` indexed `feature.geometry.coordinates[0]` as a ring (`[[lon, lat], ...]`) even when antimeridian H3 cells are `MultiPolygon` (`[[[[lon, lat], ...]]]`), producing `NaN` centroids and running linear `.features.find()` scans across ~87,815 GeoJSON features on pin clicks.

## Why It Matters
- Repeated `gc.collect()` pauses and redundant 87,815-key dictionary allocations caused false `NFR-1` latency violations, slow single-site inspection, and slow test execution.
- Returning corrupted `NaN` coordinates on antimeridian H3 cells broke fly-to navigation near ±180°, and destroying/recreating Chart.js canvases or scanning 87k GeoJSON features on click introduced avoidable frame drops.

## Rule of Thumb / What To Do Instead
- Never call `gc.collect()` inside hot paths or factory methods (`PrepackedSiteIndex.from_sites`); let Python's generational collector manage long-lived singleton indices.
- Keep `EvaluationResponse.cell_scores` lazy (`@computed_field` / `include_cell_scores=False` internally when only `ranked_results` are needed), score active parameters in L2-cache-friendly row chunks (`_SCORE_CHUNK_ROWS = 4096`), and materialize per-parameter comparisons only for the final `top_k` sites via `model_construct`.
- Cache immutable pre-serialized plain + gzipped JSON bytes on `DataStore` for static multi-megabyte GeoJSON/parameter endpoints instead of letting ASGI middleware re-encode per request.
- Index GeoJSON site centroids once in a `Map<id, [lon, lat]>` and explicitly branch `Polygon` (`coords[0]`) vs. `MultiPolygon` (`coords[0][0]`).

## References
- `src/isotopos/scoring/site_index.py`, `src/isotopos/scoring/engine.py`
- `src/isotopos/api/datastore.py`, `src/isotopos/api/app.py`
- `src/isotopos/static/js/components/globe_map.js`, `src/isotopos/static/js/components/breakdown_panel.js`, `src/isotopos/static/js/planetary_page.js`
- `decisions/DECISIONS.md` (`DEC-012`)
