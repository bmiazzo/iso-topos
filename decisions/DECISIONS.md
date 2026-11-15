# Decision Diary

A chronological log of important architectural, scientific, dataset, tooling, and scope decisions for `iso-topos` (`ER-3` in [REQUIREMENTS.md](../REQUIREMENTS.md)).

## How to Use This File
- **Read before acting:** Check existing decisions before proposing conflicting tech, schemas, or scoring changes.
- **Append-only:** Never delete or rewrite history. To change a past decision, add a new `DEC-XXX` entry and update the superseded entry's `Status` to `Superseded by DEC-YYY`.
- **What belongs here:** Tech stack choices, module/API boundaries, spatial index resolution, dataset selections, unit/scoring math, and deliberate scope trade-offs. Routine bug fixes do not belong here.

## Entry Template

```markdown
## DEC-XXX: <Short Title>
- **Date:** YYYY-MM-DD
- **Status:** Proposed | Accepted | Superseded by DEC-YYY
- **Context:** What problem or requirement forced a choice?
- **Options Considered:**
  1. Option A — pros / cons
  2. Option B — pros / cons
- **Decision:** What was chosen and why.
- **Consequences:** Downstream impacts, constraints, or follow-up work created.
- **Related:** Links to files, requirements (`FR-*`/`DR-*`/`ER-*`), or lessons learned.
```

---

## Decisions

## DEC-001: Tech Stack & Frontend/Backend Topology
- **Date:** 2026-11-14
- **Status:** Accepted
- **Context:** We need an interactive 3D Earth globe, < 500 ms re-ranking responsiveness (`NFR-1`), unified unit TDD with ~80% coverage (`ER-1`, `ER-2`), and smooth execution on standard laptops without a dedicated GPU or Node.js installed.
- **Options Considered:**
  1. Python (`FastAPI` + `Pydantic v2` + `NumPy` + `h3`) backend & ETL + Zero-Build ES Module SPA (`MapLibre GL JS` 3D Globe + `Chart.js`) — unified Python test suite, zero Node/npm install required, 60 FPS WebGL globe.
  2. Python (`FastAPI`) + React/TypeScript (`Vite`) — requires Node.js installation and dual-language test suites.
  3. Pure Python `Streamlit` — rapid prototyping, but full-script reruns cause lag/flicker on slider updates with a 3D globe.
- **Decision:** Adopt Option 1: Python 3.14 (`FastAPI`, `Pydantic v2`, `NumPy`, `h3`) for the offline ETL, scoring engine, and REST API, serving a zero-build ES Module frontend using `MapLibre GL JS` (`globe` projection) and `Chart.js`.
- **Consequences:** All backend/ETL/scoring logic is tested in a single `pytest` suite (`pytest-cov`); frontend updates only hexagon colors/properties via MapLibre `setData` without reloading the globe.
- **Related:** `REQUIREMENTS.md` (`NFR-1`, `NFR-3`, `ER-1`, `ER-2`, `ER-4`)

## DEC-002: Multi-Scale Spatial Indexing Strategy (Adaptive Earth H3 + Planetocentric Moon/Mars Grids)
- **Date:** 2026-11-14
- **Status:** Superseded by DEC-005
- **Context:** Global comparison must avoid Mercator polar distortion (`FR-4`), support arbitrary Moon/Mars `(lat, lon)` extraction (`FR-3`), capture sub-grid features like caves and impact craters (`FR-5`, `parameters.md`), and render smoothly on integrated laptop graphics.
- **Options Considered:**
  1. Adaptive H3 Land Grid (Res 2 globally + Res 3 in arid, polar, volcanic, anorthositic, alpine, and crater zones; ~4,500 cells) + 26 Curated Local Hotspots + Planetocentric `5° × 5°` `(lat, lon)` grids for Moon and Mars.
  2. Uniform H3 Res 3 across all Earth land (~12,000 cells).
  3. Uniform H3 Res 2 across all Earth land (~1,800 cells).
- **Decision:** Adopt Option 1. Adaptive H3 keeps polygon counts ~4,500 for fast rendering while preserving ~110 km detail in planetary-relevant terrains, paired with 26 sub-grid Hotspots (including speleological caves and impact craters not visible from satellites) and `5° × 5°` planetocentric bilinear grids for Moon and Mars.
- **Consequences:** `etl/spatial_builder.py` must generate valid GeoJSON polygons (handling antimeridian wrapping) and `etl/interpolator.py` must flag any non-preset `(lat, lon)` extraction as `is_extrapolated = True`.
- **Related:** `REQUIREMENTS.md` (`FR-3`, `FR-4`, `FR-5`, `FR-6`, `DR-2`), `parameters.md`

## DEC-003: Declarative 17-Parameter Schema & Two-Stage Offline ETL
- **Date:** 2026-11-14
- **Status:** Accepted
- **Context:** `FR-7` requires adding/removing analogy parameters without modifying the core ranking engine, `DR-2` forbids raw raster processing in the browser, `DR-3` requires full provenance, and `parameters.md` adds critical lunar/Martian physics (anorthosite, clays/carbonates, `0°–5°` grazing sun hours, NOAA EMAG2v3 magnetic anomalies, cold-trap sublimation, caves, and biosignatures).
- **Options Considered:**
  1. Hardcoded 10-parameter schema.
  2. Declarative `ParameterRegistry` with 17 parameters across 5 dimensions (4 Core v1 + 1 Extensible Subsurface/Biology/Ops dimension) and a two-stage offline ETL committing lightweight `data/processed/` files.
- **Decision:** Adopt Option 2. Every parameter is defined declaratively in `core/registry.py` with units, physical bounds, and NASA/partner provenance (`DR-3`). Pre-built processed JSON/GeoJSON files are committed to `data/processed/` so the app starts immediately (`NFR-3`) while `scripts/build_spatial_index.py` can regenerate them anytime.
- **Consequences:** UI sliders, layer switchers, and comparison tables are dynamically driven by `/api/v1/metadata`.
- **Related:** `REQUIREMENTS.md` (`FR-7`, `FR-8`, `FR-9`, `DR-1`, `DR-2`, `DR-3`, `NFR-3`), `parameters.md`

## DEC-004: Terrestrial-Envelope Clamped Scoring, Mission Profiles & Earth-Limit Caveats
- **Date:** 2026-11-14
- **Status:** Accepted
- **Context:** Planetary extremes (e.g., lunar polar craters at `-180 °C` or `260 °C` diurnal swings) exceed Earth's physical envelope, and some parameters (e.g., biosignature preservation) are irrelevant to Lunar base missions (`parameters.md`).
- **Options Considered:**
  1. Strict unclamped physical distance only.
  2. Terrestrial-Envelope Clamped Similarity (default) + automatic Out-of-Envelope $\Delta$ Earth-Limit Caveats + Advanced Mode toggle for Strict Absolute Distance + mission-specific default weight profiles (setting irrelevant dimensions to `0.0` $\rightarrow$ `N/A`).
- **Decision:** Adopt Option 2. Clamping target parameters to Earth's physical bounds $[E_{\min}, E_{\max}]$ by default lets Earth's closest physical frontier (e.g., East Antarctica, Greenland anorthosite) score cleanly while `DivergenceExplainer` (`FR-11`) explicitly flags the physical gap $\Delta$, gravity, vacuum/6 mbar CO₂, ice sublimation vs. melting, and pitch-black shadow caveats.
- **Consequences:** Scientists get both intuitive analog rankings and transparent physical honesty, with full control to toggle Strict mode or re-weight any parameter in Advanced Mode.
- **Related:** `REQUIREMENTS.md` (`FR-10`, `FR-11`), `parameters.md`

## DEC-005: Uniform H3 Resolution 4 Land Tiling with Natural Earth 50m Coastline Mask, Antimeridian Splitting, and Pre-Packed NumPy Scoring
- **Date:** 2026-11-14
- **Status:** Accepted
- **Context:** The initial `DEC-002` spatial index used coarse lat/lon bounding boxes (`_is_earth_land`), mixed H3 Res 2 and Res 3 cells, and dropped cells crossing `±180°`. This caused open ocean regions (North Atlantic, Mediterranean, Red Sea, Southern Ocean) to be tiled, missed coastlines/islands, left vertical holes along the `±180°` antimeridian, and created jagged aperture-7 gaps/overlaps between Res 2 and Res 3 hexagons.
- **Options Considered:**
  1. Keep Adaptive H3 (Res 2 + Res 3) with a real coastline mask — fixes ocean tiles but retains aperture-7 seam gaps between Res 2 and Res 3 hexagons.
  2. Uniform H3 Resolution 3 (~12,000 land cells, ~69 km edge) with Natural Earth coastline mask.
  3. Uniform H3 Resolution 4 (~80,000 land cells, ~26 km edge) with Natural Earth 50m Land & Minor Islands polygons (`contain="overlap"`), antimeridian `MultiPolygon` splitting, lean GeoJSON geometry, and a pre-packed `float64`/`float32` NumPy matrix (`PrepackedSiteIndex`) in `AnalogScoringEngine`.
- **Decision:** Adopt Option 3. Uniform H3 Resolution 4 is 49× finer in area than Res 2, hugs coastlines and islands naturally with zero Res 2/3 seam gaps and zero open-ocean tiles, and still evaluates in `< 25 ms` on the backend using a pre-packed `(N_sites × 17)` NumPy matrix and HTTP GZip compression.
- **Consequences:** `data/raw/` vendors `ne_50m_land.geojson` and `ne_50m_minor_islands.geojson`; `etl/spatial_builder.py` uses `h3.polygon_to_cells_experimental` and splits antimeridian hexagons into valid `MultiPolygon` rings; `api/app.py` exposes `/api/v1/site/{site_id}` and `/api/v1/earth-grid/parameter/{param_id}` so any of the ~80,000 H3 cells can be clicked or colored by raw physical parameter without bloating the GeoJSON payload.
- **Related:** `REQUIREMENTS.md` (`FR-4`, `FR-13`, `NFR-1`, `DR-2`), supersedes Earth H3 portion of `DEC-002`.

## DEC-006: Smooth Geodesic RBF Spatial Synthesis, Feature-State Updates & Auto-Contrast Color Scaling
- **Date:** 2026-11-14
- **Status:** Accepted (Heuristic synthesis and 1° well-known exclusion mask superseded by DEC-011; `setFeatureState` and auto-contrast retained and extended in DEC-011)
- **Context:** Hard axis-aligned `lat/lon` bounding boxes in `_synthesize_earth_cell_parameters` and `_synthesize_planetary_point` produced visible rectangular clusters on the globe with discontinuous jumps (e.g., `+3522 m` elevation at `27° N`, `+0.47` aridity at `16° N`, `-0.68` anorthosite at `-42° W`). Meanwhile, fixed `[0, 100]` color interpolation compressed real similarity scores (typically `35%–85%`) into narrow mid-palette hues, and `map.isStyleLoaded()` silently blocked UI menu updates while NASA GIBS raster tiles loaded.
- **Options Considered:**
  1. Keep fixed `[0, 100]` color mapping and GeoJSON `setData` calls while smoothing only a few boxes.
  2. Replace all axis-aligned `lat/lon` boxes with smooth spherical/geodesic Gaussian RBF provinces and sigmoid transitions, flag H3 cells within `1.0°` of well-known baseline hotspots, switch Earth H3 coloring to `promoteId` + `setFeatureState`, and default the color legend to `Auto-Contrast (Data Min–Max)` with an optional `Fixed 0–100%` mode.
- **Decision:** Adopt Option 2. Smooth geodesic RBF fields eliminate rectangular artifacts across all continents and planetary bodies, `setFeatureState` avoids re-tiling 28 MB of GeoJSON on every menu/slider update, `mapReady` replaces `isStyleLoaded()` so all UI controls apply immediately, and `Auto-Contrast` makes similarity differences across Earth visually distinct while displaying exact `[min, mid, max]` legend ticks.
- **Consequences:** `data/processed/*` must be regenerated whenever physiographic provinces change; `earth-h3-outline` visibility uses `line-opacity` `feature-state` expressions instead of layer `filter`.
- **Related:** `REQUIREMENTS.md` (`FR-4`, `FR-6`, `FR-13`, `NFR-1`, `NFR-4`), `src/isotopos/etl/spatial_builder.py`, `src/isotopos/static/app.js`

## DEC-007: Dynamic Tile-Variable & Python Evaluation Function Prompt Modeling for AI Mission Weight Calibration
- **Date:** 2026-11-14
- **Status:** Accepted
- **Context:** Users need to describe a planetary mission in plain text and have an AI model return calibrated `[0.0, 1.0]` weights for all registered tile parameters (`FR-7`, `FR-10`, `FR-12`).
- **Options Considered:**
  1. Static hardcoded prompt describing the 17 parameters.
  2. Dynamic prompt built from `ParameterRegistry` (`TileVariableModel` with empirical `PrepackedSiteIndex` Earth tile stats) + an explicit Python reference model of `AnalogScoringEngine` (`PYTHON_EVALUATION_FUNCTION_MODEL`), paired with a provider-agnostic `httpx` REST client (`GeminiRESTClient` by default via `GEMINI_API_KEY`, or `OpenAICompatibleRESTClient` via `OPENAI_API_KEY`/`LLM_BASE_URL`) returning validated JSON parameter weights.
- **Decision:** Adopt Option 2. Generating the prompt dynamically from `ParameterRegistry` and `PrepackedSiteIndex` preserves `FR-7` extensibility and grounds the AI in how each weight mathematically drives `evaluate_tile_score`, while `httpx` avoids adding heavy vendor SDK dependencies.
- **Consequences:** `POST /api/v1/weights/evaluate` accepts `{"mission_description": "..."}` and returns `{"weights": {...}}` validated to `[0.0, 1.0]` with an all-zero guard (`FR-10`), immediately syncing the UI weight sliders and re-ranking the 3D globe.
- **Related:** `REQUIREMENTS.md` (`FR-7`, `FR-10`, `FR-12`, `ER-1`, `ER-4`), `src/isotopos/scoring/mission_weights.py`, `src/isotopos/scoring/llm_client.py`

## DEC-008: Joint-Span Strict Mode Normalization, Order-Independent Kernel Anchor Blending & Modular ETL/Scoring Split
- **Date:** 2026-11-14
- **Status:** Accepted (Anchor blending superseded by DEC-011; joint-span strict normalization and modular ETL/scoring split retained)
- **Context:** Auditing the ETL pipeline and `AnalogScoringEngine` revealed four issues: (1) `ScoringMode.STRICT` divided unclamped target distances by Earth-only `span = earth_max - earth_min`, clipping similarity to `0.0` across all 87,815 Earth H3 cells whenever a planetary parameter exceeded Earth's bounds by $\ge 1 \times \text{span}$ (e.g., `diurnal_amplitude_c` on 11/12 presets); (2) sequential in-place blending of nearby presets/hotspots caused later entries (`malapert_massif` at `-86°`) to overwrite earlier ones (`shackleton_rim` at `-89.9°`); (3) `compute_grazing_sun_hours` omitted polar horizon/twilight grazing and hotspot blending, capping Earth H3 cells at `950 hrs/yr` vs. `1,950 hrs/yr` in hotspots; and (4) `spatial_builder.py` and `engine.py` mixed multiple responsibilities in large monolithic files.
- **Options Considered:**
  1. Keep Earth-only `span` in `STRICT` mode and sequential blending loops while patching individual preset orderings.
  2. Expand `STRICT` mode's normalization span to the joint physical envelope $\text{eff\_span}_j = \max(E_{\max,j}, T_j) - \min(E_{\min,j}, T_j)$, auto-normalize `ParameterComparison.weight` across active parameters (`FR-10`), replace sequential blending loops with symmetric order-independent Gaussian/inverse-distance kernel blending (`blend_with_anchors`), calibrate polar grazing sun hours across Earth/Moon/Mars, and split `etl/` (`geodesic_math.py`, `h3_geometry.py`, `parameter_synthesizer.py`, `spatial_builder.py`) and `scoring/` (`site_index.py`, `engine.py`, `explainer.py`) along single-responsibility boundaries (`ER-4`).
- **Decision:** Adopt Option 2. Joint-span normalization ensures `STRICT` mode penalizes out-of-envelope targets proportionally while strictly preserving relative physical ordering across Earth sites; symmetric kernel blending preserves exact preset characteristics at their coordinates; and the modular split keeps each unit focused on a single axis of change.
- **Consequences:** `data/processed/*` is regenerated with order-independent blending and calibrated polar grazing hours; `ParameterComparison.weight` always reflects normalized active weight in `[0.0, 1.0]`; disabled (`0.0`-weight) parameters no longer trigger `envelope_exceeded` caveats.
- **Related:** `REQUIREMENTS.md` (`FR-3`, `FR-10`, `FR-11`, `ER-1`, `ER-4`), `DEC-004`, `DEC-006`, `lessons-learned/2026-11-14-strict-mode-span-zeroing-and-sequential-blending.md`

## DEC-009: Modular Zero-Build Frontend Decomposition & Multi-Level Collapsible Menu Architecture
- **Date:** 2026-11-15
- **Status:** Accepted
- **Context:** The original frontend placed all state, API calls, MapLibre setup, canvas drawing, and DOM manipulation in a monolithic 1,324-line `app.js` and 608-line `styles.css`. Menus were flat and non-collapsible, causing panels to overflow with native browser side scrollbars, and making future menu additions/nesting error-prone (`ER-4`).
- **Options Considered:**
  1. Introduce a Node/Vite/React build toolchain.
  2. Keep the zero-build ES Module SPA (`DEC-001`) while decomposing CSS into layered `@import` files (`styles/tokens.css`, `layout.css`, `menus.css`, `components.css`) and JS into single-responsibility ES modules (`js/state.js`, `js/api.js`, `js/ui/collapsible.js`, `js/ui/menu_summaries.js`, `js/components/*`), backed by a declarative `createCollapsibleSection` factory, `MenuCollapseController`, `SidebarController`, `localStorage` persistence, and hidden scrollbars (`.no-scrollbar`).
- **Decision:** Adopt Option 2. Native browser ES Modules and CSS `@import` layers preserve zero-Node startup (`NFR-3`, `DEC-001`) while enforcing SOLID boundaries (`ER-4`) so new Level-1/2/3 menus, dimensions, or overlays can be added declaratively without modifying core orchestration.
- **Consequences:** All sidebars (0px collapsed width with floating reopen pills), Level-1 cards, Level-2 nested sub-menus, Level-3 dynamic dimension groups, and floating globe overlays share one uniform collapsible contract; MapLibre `resize()` and Chart.js `resize()` hook cleanly into sidebar and panel transitions.
- **Related:** `REQUIREMENTS.md` (`FR-13`, `FR-14`, `FR-15`, `NFR-3`, `ER-4`), `DEC-001`, `src/isotopos/static/js/ui/collapsible.js`

## DEC-010: SOLID API/Scoring/Frontend Sub-Module Decomposition & Singleton DataStore Caching
- **Date:** 2026-11-15
- **Status:** Accepted
- **Context:** A SOLID and web-guidance audit identified mixed responsibilities in `api/app.py` (mixing DTO schemas, disk I/O, CSV/JSON serialization, and HTTP routing), `scoring/explainer.py` (hardcoded `if` chains for exploration relevance and body caveats), `etl/parameter_synthesizer.py` (branching Moon/Mars synthesis in one function), and `static/js/components/globe_map.js` (537 lines mixing starfield rendering, color scale expression math, and MapLibre lifecycle). In addition, instantiating `DataStore` freshly on every `create_app()` call caused the test suite to reload ~50 MB of JSON nine times.
- **Options Considered:**
  1. Leave `api/app.py` and `globe_map.js` as single files and only patch individual UI bugs.
  2. Split `api/` into `schemas.py`, `datastore.py` (with `get_default_datastore()` singleton caching and injectable `store`), `exporters.py` (`EXPORTERS` strategy table), and `app.py`; make `DivergenceExplainer` rule-driven (`ExplorationRelevanceRule`, `BODY_CAVEAT_SPECS`); dispatch planetary synthesis via `_PLANETARY_SYNTHESIZERS`; and split frontend rendering into `ui/dom.js`, `components/starfield.js`, `components/color_scale.js`, `components/target_panel.js`, and `components/globe_map.js`.
- **Decision:** Adopt Option 2. Each module now has a single axis of change (SRP) and uses strategy registries (`EXPORTERS`, `_PLANETARY_SYNTHESIZERS`, `ExplorationRelevanceRule`) for open/closed extensibility (OCP).
- **Consequences:** Full `pytest` execution time dropped from ~35 s to ~9.5 s with 93.2% coverage; frontend DOM rendering is HTML-escaped and keyboard/ARIA-accessible; in-flight `/api/v1/rank` calls are guarded by `rankSeq` against race conditions.
- **Related:** `REQUIREMENTS.md` (`FR-11`, `FR-13`, `FR-15`, `ER-1`, `ER-2`, `ER-4`), `.agents/skills/solid-principles/SKILL.md`

## DEC-011: Real Auth-Free Open Dataset ETL Pipeline, Independent Site Evaluation, 3D Planetary Selector (`/planetary`), Visualization Upgrade & Full-Earth Evaluation
- **Date:** 2026-11-15
- **Status:** Accepted
- **Context:** Auditing the initial `DEC-006`/`DEC-008` spatial index revealed three interrelated flaws: (1) synthetic field synthesis in `parameter_synthesizer.py` produced diagonal sinusoidal electromagnetic striping (`abs(n3)`) and smeared local hotspot anomalies across 4.5° radii (`blend_with_anchors`), leaking zero-sunlight cave values (e.g., Mt. Etna) across Sicily; (2) the `is_near_well_known_baseline(..., radius_deg=1.0)` novelty mask flagged only `124 / 87,815` Earth H3 cells (0.14%), leaving top rankings in Antarctica, Atacama, Iceland, and Hawaii virtually untouched when "Beyond Well-Known Sites" was enabled; and (3) globe markers/labels and planetary target picking lacked visual prominence, photo context, and 3D planetary exploration. Partially supersedes `DEC-006` (heuristic proxy synthesis and 1° well-known exclusion mask) and `DEC-008` (anchor kernel blending).
- **Options Considered:**
  1. Patch individual heuristic formulas and expand only hotspot exclusion radii.
  2. Replace synthetic heuristics and anchor blending with real, auth-free open global/planetary gridded datasets fetched offline (`scripts/fetch_open_datasets.py` -> gitignored `data/raw/`) and aggregated independently per site (`scripts/build_spatial_index.py` -> `data/processed/`), add interpolation provenance flags + `p2–p98` auto-contrast scaling, enforce full-region baseline exclusion masks with visual globe dimming, build a dedicated `/planetary` 3D Moon/Mars target selector page, upgrade Earth globe ranked pins + drawer tabs + dual site-photo/satellite previews, and lock guarantees with a 4-pillar `@pytest.mark.full_earth` evaluation suite.
- **Decision:** Adopt Option 2.
  - **Real Earth Grids (`-90°..+90°`):** NOAA EMAG2v3 `SeaLevel` (`|ΔB|`, nT) with sentinel (`99999`/`-888`/`-999`/`NaN`) filtering and spherical-neighbor track-gap interpolation tracked in `EarthSite.interpolated_parameters`; NOAA ETOPO2v2c 2-arcmin global elevation & slope/roughness (covering Antarctica cleanly where WorldClim elev zeroes below -60°); WorldClim v2.1 BIO1/BIO2/BIO12 + `srad`; GLiM v1.0 0.5° global lithology (`hartmann-moosdorf_2012.zip`); MODIS `MCD12C1` land cover (`Zenodo 6350821`) barren/snow-ice fractions; Global Aridity Index v3 (`Zenodo 10074189`); Obu et al. (2019) Northern Hemisphere permafrost (`PANGAEA 888600`) paired with Antarctic/Andean cryosphere coverage; Natural Earth 50m Admin-0 country/region enrichment (`country`, human-readable H3 labels).
  - **Real Moon & Mars Grids:** LRO LOLA (`ldem_4`, `ldsm_16`, `ldrm_16`), LRO Diviner (`dgdr_ra_avg`, `dgdr_st_avg`), Lunar Prospector GRS (`lpgrs_high1_elem_abundance_2deg.tab`), Tsunakawa et al. (2015) lunar spherical harmonic magnetic model (`Zenodo 3873648`); MGS MOLA (`megt90n000cb`), MGS TES (`global_albedo_8ppd`, `global_ti_night_2007`), Mars Odyssey GRS (`h2o`, `fe`, `si`, `cl`), and Langlais et al. (2019) Martian crustal magnetic model (`Zenodo 3876714`).
  - **Zero Anchor Blending (`FR-5` preserved):** H3 macro-cells never inherit hotspot anomalies (`blend_with_anchors` removed); named hotspots update shared regional physical metrics from real datasets at exact coordinates while retaining local sub-grid catalog scores.
  - **Full-Region Novelty Mask (`FR-6`) & `/planetary` + Visualization:** Flag full Antarctica, Iceland, Hawaii, Atacama corridor, Devon Island/Haughton, and Rio Tinto in ETL and `earth_h3_grid.geojson`; dim excluded cells visually on the globe, auto-reselect if needed, display excluded counts, render ranked pins for both Top-K H3 regions and named sites, support `Auto (p2–p98)` / `Full Min–Max` / `Log` / `Fixed` scales without masking `raw:` layers, and serve `/planetary` with 3D NASA Trek / OpenPlanetary basemaps and local fallback.
- **Consequences:** All `~87,815` Earth H3 cells and planetary grids reflect real geophysical measurements with full agency/URL/interpolation provenance and `<100 ms` online scoring latency, verified on every `pytest` run via `@pytest.mark.full_earth`. Offline raw downloads (~350 MB total) stay gitignored while small `data/processed/*` artifacts remain committed for instant startup.
- **Related:** `REQUIREMENTS.md` (`FR-3`, `FR-5`, `FR-6`, `FR-10`, `FR-11`, `DR-1..DR-4`, `NFR-1..NFR-3`, `ER-1..ER-4`), `DEC-006`, `DEC-008`, `tests/evaluation/test_full_earth_evaluation.py`

## DEC-012: Lazy `EvaluationResponse.cell_scores`, L2-Chunked Active Scoring, Cached API Payloads, and Removal of `gc.collect()`
- **Date:** 2026-11-15
- **Status:** Accepted
- **Context:** Profiling the full codebase and `NFR-1` (`< 100 ms` online scoring latency across `~87,815` Earth H3 cells) revealed three major bottlenecks: (1) `PrepackedSiteIndex.from_sites` called `gc.collect()` unconditionally on every single-site or prepacked instantiation, triggering a ~1.1 s full-generation GC pause whenever `DataStore` held ~88k loaded `EarthSite` + GeoJSON objects; (2) `AnalogScoringEngine.evaluate_prepacked` spent ~52–86 ms building an 87,815-entry `dict[str, float]` (`dict(zip(...))`), allocating full ~11.9 MB `float64` matrix temporaries, and running Pydantic validation across 255+ per-parameter breakdown objects even when callers only used `ranked_results` or top-k scores; and (3) `GET /api/v1/earth-grid` and `/api/v1/earth-grid/parameter/{param_id}` re-serialized static 35 MB / ~1.5 MB JSON payloads via FastAPI's encoder on every request. In addition, frontend `resolveSiteCoords` mishandled antimeridian `MultiPolygon` geometries via linear `.features.find()`, Chart.js instances were destroyed/recreated on every click, planetary slices recomputed `hexToRgb` per pixel, and `rAF` loops spun continuously even when paused or hidden.
- **Options Considered:**
  1. Keep eager `dict(zip(...))` materialization in `EvaluationResponse` and add ad-hoc caching only on the HTTP route layer.
  2. Remove `gc.collect()` from `PrepackedSiteIndex.from_sites`; precompute matrix index/midpoint arrays in `AnalogScoringEngine.__init__` and score active parameters in L2-cache-friendly row chunks (`_SCORE_CHUNK_ROWS = 4096`) without strided column copies when density is high; cache pre-filtered `novel` slices and dict templates on `PrepackedSiteIndex`; make `EvaluationResponse.cell_scores` a lazily materialized `@computed_field` with `include_cell_scores: bool = True`; cache pre-serialized plain + gzipped JSON payloads (`gzip` level 5) on `DataStore` (seeding `earth_grid` directly from disk bytes when present); and refactor frontend spin loops, Chart.js updates, coordinate lookups, and 256-entry RGB palette LUTs.
- **Decision:** Adopt Option 2. Preserves exact `EvaluationResponse` wire compatibility (eager when serialized for `/api/v1/rank`, zero dict allocation when skipped internally or in `/api/v1/export`) while cutting full-Earth ranking work to L2-chunked vectorized math plus top-k breakdowns, eliminating `gc.collect()` pauses in single-site inspection, and serving immutable geospatial grids from pre-compressed caches.
- **Consequences:** All existing API schemas and scoring outputs remain bit-identical (`test_pillar4_full_preset_ranking_novelty_mask_and_nfr1_latency` passes across all 12 presets well under `100 ms`), `evaluate_single_site()` avoids building a throwaway `PrepackedSiteIndex`, and headless static GeoJSON/parameter endpoints avoid repeated multi-megabyte JSON encoding.
- **Related:** `REQUIREMENTS.md` (`NFR-1`, `ER-2`, `ER-4`), `DEC-005`, `DEC-010`, `lessons-learned/2026-11-15-gc-collect-and-eval-response-dict-overhead.md`






