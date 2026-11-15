# iso-topos

> **Identify and characterize terrestrial analog locations on Earth for permanent Moon-base locations, Moon landing sites, and future Mars landing/exploration sites using open NASA and partner space-agency datasets.**

---

## Overview

`iso-topos` (*equal place*) is a transparent, scientist-oriented interactive web application built for the **"Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars"** challenge ([challengeDetails.md](resouces/challengeDetails.md)).

Rather than treating terrestrial analogs as black-box similarity scores or purely visual lookalikes, `iso-topos` compares planetary targets (Moon and Mars) against Earth using **17 physically grounded parameters across 5 dimensions**, unit-level comparisons, full dataset provenance (`DR-3`), and explicit **Earth-limit caveats** (such as reduced gravity, lunar vacuum, thin 6 mbar Martian CO₂ atmosphere, ice sublimation vs. melting, and pitch-black lunar shadows).

---

## Core Capabilities

- **Planetary → Earth Analog Search (`FR-1`–`FR-3b`):**
  - **12 Curated Moon & Mars Target Presets:** *Shackleton Crater Rim*, *Mons Mouton Plateau*, *Malapert Massif*, *Aristarchus Plateau*, *Mare Tranquillitatis Skylight Pit*, *Reiner Gamma Swirl*; *Arcadia Planitia*, *Jezero Crater Delta*, *Oxia Planum*, *Mawrth Vallis*, *Gale Crater*, and *Arsia Mons Flank Pit Caves*.
  - **Dedicated 3D Planetary Explorer (`/planetary`):** Interactive CesiumJS 3D Moon & Mars globes (NASA Trek WMTS `LRO_LOLA_Shade_Global_128ppd_v04` polar-complete shaded relief, `LRO_WAC_Mosaic`, & Mars *Viking MDIM2.1*) with selectable basemaps, gridded parameter overlays, and arbitrary `(lat, lon)` bilinear extraction.
- **Multi-Scale 3D Globe Discovery (`FR-4`–`FR-6`, `DR-1a`):**
  - **CesiumJS 3D Earth Globe** (with 2D map toggle) rendering **89,022 Uniform H3 Resolution-4 Land Hexagons** and **26 Curated Local Hotspots** (including *White Mountain / Qaqortorsuaq* in Greenland, *Grotta del Gelo* on Mt. Etna, *Mistastin Crater*, *Lofoten*, *Batagaika*, *Lake Salda*, *Pilbara / Shark Bay*, and *Svalbard*).
  - **Multi-Layer Switcher:** Color the globe by Overall Similarity, any Dimension Sub-Score, or any of the 17 Raw Physical Parameters, layered over **NASA GIBS** satellite imagery (*Blue Marble Next Generation* / *MODIS Terra True Color*).
  - **"Beyond Well-Known Sites" Filter:** Hide or dim classic baselines (Atacama, McMurdo, Haughton, Mauna Loa, Askja, Rio Tinto) to surface under-studied analogs.
- **Dual-Mode Scientist UI (`FR-13`–`FR-15`):**
  - **Simple Mode:** Preset/coordinate selector, 3D Earth Globe, and Site Breakdown Card (Dimension bar chart, Earth-limit caveats, and exploration relevance).
  - **Advanced Mode:** Seamless parameter pre-fill, direct parameter overrides, `0–100%` weight sliders and disable toggles (`N/A` dimension guard), Terrestrial-Clamped vs. Strict Physical Distance toggle, physical range filters, full provenance citation table, and **CSV/JSON export**.

---

## Quick Start (`NFR-3`)

### 1. Create Environment & Install Dependencies
```bash
python3 -m venv .venv
.venv/bin/pip install fastapi uvicorn pydantic numpy h3 pytest pytest-cov httpx
echo "$(pwd)/src" > .venv/lib/python3.14/site-packages/isotopos.pth
```

### 2. Run the Offline ETL Spatial Index Builder (Optional — Pre-built in `data/processed/`)
```bash
.venv/bin/python scripts/build_spatial_index.py
```

### 3. Run Unit & Integration Tests with Coverage ($\ge 80\%$)
```bash
.venv/bin/pytest --cov=isotopos --cov-report=term-missing --cov-fail-under=80
```

### 4. Start the Application Server
```bash
.venv/bin/uvicorn isotopos.api.app:app --host 127.0.0.1 --port 8000
```
Open **http://127.0.0.1:8000** in your browser.

---

## Repository Layout

```text
iso-topos/
├── src/isotopos/
│   ├── core/          # Declarative ParameterRegistry, models & DR-3 provenance
│   ├── scoring/       # Vectorized NumPy AnalogScoringEngine & DivergenceExplainer
│   ├── etl/           # Uniform H3 Res-4 builder, Moon/Mars grids, interpolator & catalogs
│   ├── api/           # FastAPI REST endpoints & CSV/JSON export
│   └── static/        # Zero-build ES Module 3D Globe Scientist UI
├── scripts/           # Offline ETL generator (build_spatial_index.py)
├── data/processed/    # Committed lightweight JSON/GeoJSON spatial indices
├── tests/             # Unit & integration TDD test suite
├── decisions/         # Decision Diary (DECISIONS.md)
└── lessons-learned/   # Lessons Learned index
```
