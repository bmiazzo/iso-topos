# iso-topos

> **Identify and characterize terrestrial analog locations on Earth for permanent Moon-base locations, Moon landing sites, and future Mars landing/exploration sites using open NASA and partner space-agency datasets.**

> [!NOTE]
> **Status — Specification & Planning Phase (Temporary Placeholder)**
> This repository is currently in its pre-implementation planning phase. The project structure, tech stack, and setup instructions below are temporary and will be finalized once implementation begins and architectural choices are logged in the [Decision Diary](decisions/DECISIONS.md).

---

## Overview

`iso-topos` (*equal place*) is a transparent, scientist-oriented interactive web application built for the **"Identify Earth Locations that Analog the Permanent Moon Base Locations and Mars"** challenge ([challengeDetails.md](resouces/challengeDetails.md)).

Rather than treating terrestrial analogs as black-box similarity scores or purely visual lookalikes, `iso-topos` compares planetary targets (Moon and Mars) against Earth using physically grounded dimensions, unit-level comparisons, full dataset provenance, and explicit **Earth-limit caveats** (such as reduced gravity, lunar vacuum, thin Martian CO₂ atmosphere, and radiation).

---

## Planned Core Capabilities

Full functional and engineering specifications live in [REQUIREMENTS.md](REQUIREMENTS.md). At a glance, the v1 design targets:

- **Planetary → Earth Analog Search:**
  - Select from **6–10 curated Moon and Mars target presets** (e.g., Shackleton Crater Rim, Malapert Massif, Aristarchus Plateau; Jezero Crater, Gale Crater, Arcadia Planitia, Mawrth Vallis), or pick any arbitrary `(lat, lon)` coordinate on the Moon or Mars (including an interactive 2D planetary map picker).
  - Extrapolated/interpolated target values are transparently flagged.
- **Multi-Scale Spatial Discovery:**
  - Distortion-resistant global Earth spatial grid (e.g., H3 hexagonal cells) paired with curated high-resolution **local hotspot overlays** (craters, lava tubes, caves, salt flats) and filters to look **beyond well-known analog sites** (such as Atacama, Antarctica, Iceland, and Hawaii).
- **Extensible Analogy & Scoring Engine (v1 Dimensions):**
  1. **Topography & Terrain** (elevation, slope, roughness, landform proxies)
  2. **Geology & Mineralogy** (rock/soil classes, basalt/regolith analogs, mineralogical proxies)
  3. **Temperature & Illumination** (thermal extremes, diurnal/seasonal swings, solar angle/illumination proxies)
  4. **Water, Ice & Permafrost** (subsurface ice, permafrost, aridity, hydration proxies)
- **Dual-Mode Scientist UI:**
  - **Simple Mode:** Target preset or coordinate selector, interactive ranked Earth map, and Site Breakdown Card (overall score, per-dimension breakdown, Earth-limit caveats, and exploration/testing relevance).
  - **Advanced Mode:** Seamless pre-fill from Simple Mode, per-parameter value overrides, live `0–100%` weight sliders and disable toggles, physical range filters, raw unit-level comparison tables with dataset citations, and CSV/JSON export.

---

## Data Sources & Architecture Principles

- **Open Scientific Datasets ([challengeResources.md](resouces/challengeResources.md)):** Grounded in open NASA Earthdata and Planetary Data System (PDS) / LRO & MRO products, supplemented where helpful by CSA (RADARSAT/RCM), ESA (Copernicus / Open Science Catalog), JAXA (G-Portal), and other open geoscience datasets.
- **Offline Heavy ETL / Thin Client:** All heavy raster processing (GeoTIFF, NetCDF, HDF5) runs in an offline ETL pipeline; the browser only consumes lightweight pre-aggregated JSON/GeoJSON or vector tile payloads.
- **Full Provenance:** Every metric carries source agency/mission, dataset name, reference URL, physical unit, and spatial/temporal resolution.

---

## Repository Layout (Current)

```text
iso-topos/
├── README.md                  # Project overview (temporary structure)
├── REQUIREMENTS.md            # Functional, data, non-functional & engineering specs
├── AGENTS.md                  # Instructions and guardrails for AI coding agents
├── decisions/
│   └── DECISIONS.md           # Living Decision Diary (architectural & scientific trade-offs)
├── lessons-learned/
│   └── INDEX.md               # Index of surprising discoveries and hard-won lessons
├── resouces/
│   ├── challengeDetails.md    # Challenge prompt and evaluation considerations
│   └── challengeResources.md  # NASA, CSA, ESA, and JAXA open data portals
└── .agents/
    └── skills/                # Project-specific agent skills (e.g., solid-principles)
```

---

## Getting Started (Placeholder)

> *Setup, build, ETL pipeline execution, and test commands will be added here once the tech stack is chosen and recorded in [decisions/DECISIONS.md](decisions/DECISIONS.md).*

For now, start by reading:
1. [REQUIREMENTS.md](REQUIREMENTS.md) — full scope and acceptance priorities (Must / Should / Could)
2. [AGENTS.md](AGENTS.md) — workflow rules, TDD/coverage targets, Decision Diary, and Lessons Learned
3. [decisions/DECISIONS.md](decisions/DECISIONS.md) — current architectural and dataset decisions
