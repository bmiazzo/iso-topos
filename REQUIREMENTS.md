# iso-topos — Project Requirements

> **Mission:** Identify and characterize terrestrial analog locations on Earth for permanent Moon-base locations, Moon landing sites, and future Mars landing/exploration sites using open NASA and space-agency datasets, presented through a transparent, scientist-oriented interactive web application.

---

## 1. Context & Target Audience

- **Origin:** Built for the *"Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars"* challenge ([challengeDetails.md](resouces/challengeDetails.md)), using open datasets and portals cataloged in [challengeResources.md](resouces/challengeResources.md).
- **Target Users:** Planetary scientists, mission planners, and astrobiology/robotics researchers who require physical transparency, unit-level comparisons, and explicit scientific caveats rather than black-box scores.
- **Hackathon Constraint:** Requirements are prioritized (Must / Should / Could) to ensure a reliable, end-to-end working demo before the end of the hackathon, while keeping the architecture clean and extensible.
- **Tech Stack:** Intentionally technology-agnostic in this document; implementation choices will be recorded in the Decision Diary.

---

## 2. Functional Requirements

### 2.1 Planetary Targets, Coordinate Extraction & Presets
- **FR-1 (Must) — Dual Planetary Support (Planetary → Earth Search):** Support selecting a target site on either **Moon** (candidate permanent base locations and landing sites) or **Mars** (candidate landing and exploration sites) and returning ranked terrestrial analogs on Earth. Reverse search (selecting an Earth site to find similar Moon/Mars sites) is **not required**.
- **FR-2 (Must) — Curated Target Catalog (Presets):** Include **6–10 real candidate Moon and Mars target sites** (e.g., Shackleton Crater Rim, Malapert Massif, Aristarchus Plateau; Jezero Crater, Gale Crater, Arcadia Planitia, Mawrth Vallis) populated from open planetary datasets (e.g., LRO/LOLA, MRO/MOLA/CRISM).
- **FR-3 (Must) — Arbitrary Moon/Mars Coordinate Parameter Extraction:** Allow users to pick an arbitrary `(lat, lon)` location on the Moon or Mars; the system extracts or extrapolates the corresponding target parameter values from pre-processed planetary spatial grids and feeds them into the **same** Earth evaluation algorithm. Any interpolated or extrapolated values must be transparently flagged to the scientist.
- **FR-3a (Should) — Interactive 2D Moon/Mars Map Picker:** Provide a clickable 2D Moon/Mars map in addition to `(lat, lon)` coordinate input for selecting arbitrary planetary locations.
- **FR-3b (Must) — Seamless Simple → Advanced Pre-fill:** Selecting a Moon/Mars preset or arbitrary coordinate in Simple mode must pre-fill the target parameter vector so the user can switch to Advanced mode to inspect, override, or fine-tune any parameter before re-running the evaluation algorithm.

### 2.2 Spatial Index & Discovery
- **FR-4 (Must) — Global Spatial Grids (Earth, Moon & Mars):** Partition Earth into a pre-processed, distortion-resistant global spatial index (e.g., H3 hexagonal cells) for fair polar and mid-latitude comparison, and pre-process Moon and Mars datasets into lightweight backend spatial grids to support fast parameter extraction/extrapolation for arbitrary coordinates.
- **FR-5 (Must) — Local Hotspot Overlays:** Support overlaying curated high-resolution local features (e.g., specific impact craters, lava tubes, caves, salt flats) that are smaller than a grid cell, enabling multi-scale discovery.
- **FR-6 (Should) — Beyond Well-Known Sites:** Support filtering or highlighting lesser-known / under-studied regions (e.g., excluding or de-prioritizing well-known baseline sites like Atacama, Antarctica, Iceland, Hawaii) to surface previously unrecognized analogs.

### 2.3 Extensible Analogy & Scoring Engine
- **FR-7 (Must) — Pluggable Dimension Framework:** Implement a modular, plugin-style dimension interface so new analogy parameters can be added without modifying the core ranking engine.
- **FR-8 (Must) — Core v1 Analogy Dimensions:** Support the following four dimensions in v1:
  1. **Topography & Terrain** (elevation, slope, surface roughness, crater/landform proxies)
  2. **Geology & Mineralogy** (rock/soil classes, basalt/regolith analogs, mineralogical proxies)
  3. **Temperature & Illumination** (thermal extremes, diurnal/seasonal swings, solar angle/illumination proxies)
  4. **Water, Ice & Permafrost** (subsurface ice, permafrost, aridity, hydration proxies)
- **FR-9 (Could) — Future Extensible Dimensions:** Architecture must readily accommodate additional dimensions post-MVP, such as:
  - Dust, wind, and aeolian/erosional processes
  - Subsurface & caves (lava tubes, mines, underground habitats)
  - Biology, extremophiles, habitability, and vegetation masks
  - Operational & engineering constraints (landing safety, mobility, accessibility)
- **FR-10 (Must) — Unified Parameter-Driven Weighted Scoring:** Implement a single evaluation algorithm that accepts any target parameter vector (whether derived from a Moon/Mars preset, extrapolated from an arbitrary Moon/Mars coordinate, or manually entered in Advanced mode) and **per-parameter weights** (`0.0`–`1.0`, auto-normalized across active parameters). It must compute an overall similarity score plus **per-dimension sub-scores** (derived from each dimension's active parameters; `N/A` if all parameters in a dimension are disabled, and guarding against all-zero weights).
- **FR-11 (Must) — Analogy Breakdown & Divergence Explanation:** For every ranked Earth analog, explicitly surface:
  - Which dimensions match strongly and which diverge
  - Raw physical values (with units) for Earth vs. the selected Moon/Mars target
  - **Earth-limit caveats** noting where any terrestrial analog fundamentally breaks down (e.g., reduced gravity, lunar vacuum, thin Martian CO₂ atmosphere, radiation environment)
  - Suggested exploration/testing relevance (e.g., rover mobility, ISRU water extraction, thermal cycling)
- **FR-12 (Could — Stretch) — AI-Assisted Scientific Explanation:** Integrate an AI/LLM model to inspect the active dimension weights, raw physical values, and similarity/divergence scores to generate a concise natural-language scientific summary of why a site was ranked as it was and how it could be used.

### 2.4 Scientist UI (Dual-Mode Interactive Map)
- **FR-13 (Must) — Interactive Map in Both Modes:** Both Simple and Advanced interfaces must feature an interactive map displaying ranked Earth grid cells and hotspot overlays with interactive hover/click inspection, zoom/pan, and visual score encoding.
- **FR-14 (Must) — Simple Mode:**
  - Mission/target preset selector (Moon & Mars sites) and arbitrary Moon/Mars `(lat, lon)` coordinate input (plus clickable 2D Moon/Mars map as `FR-3a`)
  - Interactive Earth map showing top-ranked Earth analogs
  - Site Breakdown Card showing overall score, per-dimension breakdown chart, Earth-limit caveats, and exploration relevance (plus clear indicators when target parameters were extrapolated)
- **FR-15 (Must) — Advanced Mode:**
  - All Simple Mode capabilities, plus:
  - Direct input/override for **every** target parameter value (pre-filled when coming from a Simple Mode planetary selection)
  - **Per-parameter weight sliders** (`0`–`100%`, auto-normalized) grouped by dimension, with a quick disable (`0`-weight) toggle per parameter for live re-ranking
  - Physical range filters (e.g., max slope, temperature bounds, aridity/ice thresholds)
  - Raw unit-level comparison table (Earth site value vs. planetary/custom target value + full dataset provenance/citations including agency/mission and source URL per `DR-3`)
  - Export of ranked results and comparisons (CSV and/or JSON)

---

## 3. Data & Performance Requirements

- **DR-1 (Must) — Real Open Datasets (NASA & Partner Resources):** Use verifiable, open Earth and planetary datasets grounded in [challengeResources.md](resouces/challengeResources.md). At a minimum, the offline ETL spatial index and target catalog **must** incorporate **at least one NASA Earth resource** (e.g., via NASA Earthdata Search such as SRTM, MODIS, SMAP, or ASTER) and **at least one NASA Moon/Mars resource** (e.g., via NASA PDS / LRO such as LOLA, Diviner, LEND, or MRO/MOLA), without mandating specific portals if better-suited open access paths are available. Space agency partner resources cited in `challengeResources.md` (CSA RADARSAT/RCM, ESA Copernicus/Open Science Catalog, JAXA G-Portal) and other open scientific datasets (e.g., USGS, GLiM, ERA5, NSIDC) are encouraged as supplementary (`Should`) sources.
- **DR-1a (Should) — Optional Visual Imagery & Tile Layers:** Optionally surface pre-tiled or static visual layers from cited resources (e.g., NASA Worldview GIBS tiles for Earth, LROC/planetary basemaps for Moon/Mars) in the interactive maps (`FR-13`, `FR-3a`), provided they remain lightweight and do not violate `DR-2` or introduce auth friction (`NFR-2`).
- **DR-2 (Must) — Offline Heavy Processing / Thin Client:** All heavy geospatial raster processing (GeoTIFF, NetCDF, HDF5) must happen in an **offline ETL/indexing pipeline**. The client browser must **never** download or parse raw raster formats; it must only receive lightweight pre-aggregated JSON/GeoJSON or vector tile payloads.
- **DR-3 (Must) — Data Provenance:** Every metric stored in the spatial index and target catalog must carry metadata citing its **source agency/mission**, **dataset name**, **reference/portal URL**, **physical unit**, and **spatial/temporal resolution**. These citations must be surfaced in Advanced Mode (`FR-15`) and may optionally be shown in Simple Mode (`FR-14`).
- **DR-4 (Should) — Deterministic Test Fixtures:** Maintain a small, realistic synthetic/sampled dataset fixture for fast, deterministic unit and integration testing without requiring full global dataset downloads.

---

## 4. Non-Functional Requirements

- **NFR-1 (Must) — Interactive Responsiveness:** Re-ranking and filtering across the pre-processed spatial index should feel instantaneous (< 500 ms for typical preset/weight updates) to support live scientific exploration and demo presentation.
- **NFR-2 (Must) — No Auth Friction:** Public/open read-only access with no login or account required for the hackathon demo.
- **NFR-3 (Should) — Reproducible Local Setup:** The application and offline ETL pipeline must be runnable locally with clear, documented commands and minimal environment setup.
- **NFR-4 (Should) — Accessibility & Clarity:** Scientific units, color scales (colorblind-safe palettes recommended), and caveats must be clearly labeled on all charts and map legends.

---

## 5. Engineering & Workflow Requirements

- **ER-1 (Must) — Unit Test-Driven Development (TDD):** Core logic—especially the offline ETL aggregators, pluggable dimension scorers, normalization/distance functions, divergence explainer, and API handlers—must be developed using unit TDD (write failing unit tests before implementation).
- **ER-2 (Must) — ~80% Unit Test Coverage:** Maintain approximately **80% unit test coverage** across the codebase (enforced/measured via the chosen stack's coverage runner in CI or pre-commit checks).
- **ER-3 (Must) — Decision Diary:** Maintain a living Decision Diary (e.g., `DECISIONS.md` or `docs/decisions/`) where agents and developers record important architectural, scientific, dataset, and trade-off decisions (context, options considered, decision made, and consequences).
- **ER-4 (Must) — Modularity & Clean Boundaries:** Keep the ETL pipeline, scoring engine, API layer, and frontend UI cleanly decoupled so components can be tested independently and extended with new analogy dimensions.

---

## 6. Out of Scope for Hackathon MVP

- Real-time/live querying of external NASA Earthdata/satellite APIs during user map interactions.
- Full 3D terrain rendering or game-engine simulations.
- Automated ML training pipelines on raw planetary imagery (deferred in favor of transparent, physically grounded multi-dimensional scoring).
- Multi-user accounts, saved cloud workspaces, or collaborative editing.
- Bidirectional / reverse search (selecting an Earth location to find matching Moon or Mars sites).
