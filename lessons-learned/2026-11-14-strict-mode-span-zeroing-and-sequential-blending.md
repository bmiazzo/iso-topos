# Strict-Mode Span Zeroing & Order-Dependent Anchor Blending Pitfalls

- **Date:** 2026-11-14
- **Area / Tags:** `scoring`, `etl`, `normalization`, `spatial-synthesis`, ` physics`

## What Surprised Us
1. **Unclamped target distance divided by Earth-only span zeroes out all Earth sites:** In `ScoringMode.STRICT`, computing `clip(1.0 - abs(earth_val - target_val) / earth_span, 0.0, 1.0)` with `earth_span = earth_max - earth_min` caused any planetary parameter whose target value exceeded `[earth_min, earth_max]` by at least one `earth_span` (such as Lunar/Martian `diurnal_amplitude_c` of `74–260 °C` vs. Earth's `2–38 °C`, `span = 36 °C`, or Arsia Mons `elevation_m = 11,500 m`) to evaluate to `0.0` for **100% of Earth H3 cells and hotspots**.
2. **Sequential in-place anchor blending overwrites earlier presets:** Looping over presets/hotspots with `params[k] = (1 - w) * params[k] + w * preset.parameters[k]` meant that closely spaced lunar south-polar presets (`shackleton_rim` at `-89.9°`, `mons_mouton` at `-84.6°`, `malapert_massif` at `-86.0°`) overwrote each other in list order—causing `shackleton_rim` (`1,300 m` elevation, `24°` slope) to be synthesized at `3,971 m` elevation (`63%` overwritten by `malapert_massif`).
3. **Flat-sphere `0°–5°` solar elevation drops above the Arctic Circle:** Pure flat-horizon `0° <= elev <= 5°` hours peak at `|lat| = 66.5°` (`922.5 hrs/yr`) and decrease toward `84.5°` (`610 hrs/yr`), creating a `> 1,100 hrs/yr` mismatch against high-arctic hotspots (`1,710–1,950 hrs/yr`) and preventing any Earth H3 cell from reaching the `1,100 hrs/yr` grazing-light relevance threshold.

## Why It Matters
- In `STRICT` mode, a hyper-arid desert with a `35 °C` diurnal swing received the exact same `0.0` diurnal score as a `2.5 °C` isothermal cave, silently neutralizing the parameter across 11 of 12 presets.
- Clicking near Shackleton Rim on the lunar coordinate picker returned Malapert Massif's `~4,000 m` elevation instead of Shackleton's `1,300 m`.

## Rule of Thumb / What To Do Instead
- When evaluating unclamped (`STRICT`) similarity against out-of-envelope targets, expand the normalization span to the joint range `max(earth_max, target_val) - min(earth_min, target_val)` so all Earth sites are penalized for the physical gap while preserving monotonic ranking across Earth's gradient.
- Blend spatial anchors using a single symmetric, order-independent kernel sum (`blend_with_anchors` combining a Gaussian envelope with inverse-distance localization `(d^2 + eps^2)^-2`), never sequential in-place mutation.
- Filter `envelope_exceeded` caveats by `weight > 0.0` so disabled parameters do not generate spurious warnings.

## References
- `src/isotopos/scoring/engine.py` (`_prepare_target_and_weights`, `score_tile_scalar`)
- `src/isotopos/etl/geodesic_math.py` (`blend_with_anchors`, `compute_grazing_sun_hours`)
- `DEC-008` in `decisions/DECISIONS.md`
