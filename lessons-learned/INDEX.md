# Lessons Learned

A curated collection of **surprising, important, hard-won insights** discovered while building `iso-topos`.

> **Decision Diary vs. Lessons Learned:** Use [`decisions/DECISIONS.md`](../decisions/DECISIONS.md) for intentional architectural/scientific choices. Use this folder for *things that surprised you and matter for future work* (dataset quirks, coordinate/unit traps, library gotchas, failed assumptions).

## How to Add a Lesson
1. Create a file named `YYYY-MM-DD-<short-slug>.md` in this directory using the template below.
2. Add a row to the **Index** table in this file.
3. Keep each note focused, concrete, and actionable—skip trivial typos or routine debugging.

## Lesson Template

```markdown
# <Concise Lesson Title>

- **Date:** YYYY-MM-DD
- **Area / Tags:** e.g., `etl`, `lunar-data`, `coordinates`, `scoring`, `frontend`

## What Surprised Us
Describe the unexpected behavior, dataset quirk, or broken assumption.

## Why It Matters
Explain the impact (e.g., silent scientific inaccuracy, broken map alignment, wasted time).

## Rule of Thumb / What To Do Instead
State the concrete check, invariant, or pattern to follow going forward.

## References
- Links to affected code, datasets, tests, or `DEC-XXX` entries.
```

---

## Index

| Date | Lesson | Area / Tags | Summary |
| :--- | :--- | :--- | :--- |
| 2026-11-14 | [H3 Polar Cells & Web Mercator ±85.05° Distortion](2026-11-14-h3-polar-mercator-clipping.md) | `etl`, `h3`, `maplibre-globe` | Keep H3 GeoJSON polygons within `|lat| <= 84.95°` and `Δlon <= 90°` to avoid polar distortion in MapLibre v5 globe mode. |
| 2026-11-14 | [Natural Earth Antarctica Polygon Clamping vs. Vertex Filtering for H3](2026-11-14-natural-earth-antarctica-polar-clamping.md) | `etl`, `h3`, `natural-earth`, `antarctica` | Clamp Natural Earth polar ring vertices to `±84.5°` instead of dropping them so Antarctica's southern closing edge stays intact (`6,200` H3 Res 4 cells). |
| 2026-11-14 | [MapLibre `isStyleLoaded()` Blocking UI Updates & Axis-Aligned Grid Artifacts](2026-11-14-maplibre-isstyleloaded-and-box-artifacts.md) | `frontend`, `maplibre`, `etl` | Use `mapReady` + `setFeatureState` instead of `isStyleLoaded()`, unify click hit-testing, and use geodesic Gaussian RBFs instead of `lat/lon` boxes. |
| 2026-11-14 | [Strict-Mode Span Zeroing & Order-Dependent Anchor Blending Pitfalls](2026-11-14-strict-mode-span-zeroing-and-sequential-blending.md) | `scoring`, `etl`, `normalization` | Use joint `[min(earth_min, target), max(earth_max, target)]` spans in `STRICT` mode and order-independent kernel sums when blending nearby presets/hotspots. |
