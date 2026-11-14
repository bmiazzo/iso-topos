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
- **Status:** Accepted
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
