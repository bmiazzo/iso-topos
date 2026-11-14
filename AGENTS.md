# AGENTS.md — Repository Instructions for Coding Agents

This file defines mandatory workflow rules, knowledge-capture practices, and engineering guardrails for all AI agents working in `iso-topos`.

---

## 1. Mandatory Pre-Task Context Check

Before starting any non-trivial task (design, ETL, scoring, API, UI, or debugging):

1. Read [`REQUIREMENTS.md`](REQUIREMENTS.md) for relevant functional (`FR-*`), data (`DR-*`), non-functional (`NFR-*`), and engineering (`ER-*`) requirements.
2. Read [`decisions/DECISIONS.md`](decisions/DECISIONS.md) to align with prior architectural, scientific, dataset, and trade-off decisions.
3. Read [`lessons-learned/INDEX.md`](lessons-learned/INDEX.md) and open any lesson files relevant to the area you are modifying so you do not repeat past mistakes.

---

## 2. Decision Diary (`decisions/DECISIONS.md`)

Per `ER-3` in [`REQUIREMENTS.md`](REQUIREMENTS.md), maintain [`decisions/DECISIONS.md`](decisions/DECISIONS.md) as a single chronological log of numbered decisions (`DEC-001`, `DEC-002`, ...).

### When to Record a Decision (Proactive)
You **must** proactively append a new entry before or when completing work that makes or changes any meaningful choice, including:
- Tech stack, framework, spatial index (e.g., H3 resolution), or storage/serialization format choices.
- Architecture, module boundaries, API contracts, or data schemas.
- Planetary/Earth dataset selection, proxy definitions, unit conversions, normalization, or scoring math.
- Deliberate scope adjustments, requirement interpretations, or hackathon trade-offs.

### When NOT to Record a Decision
Do **not** log routine bug fixes, formatting/refactor edits that preserve contracts, or trivial implementation details.

### Rules for Updating `decisions/DECISIONS.md`
- **Append-only history:** Never delete or silently rewrite past decisions. If a decision changes, add a new `DEC-XXX` entry and update the old entry's `Status` to `Superseded by DEC-YYY`.
- **Follow the template** at the top of [`decisions/DECISIONS.md`](decisions/DECISIONS.md) (`Date`, `Status`, `Context`, `Options Considered`, `Decision`, `Consequences`, `Related`).
- Keep entries concise, objective, and grounded in concrete trade-offs.

---

## 3. Lessons Learned (`lessons-learned/`)

Keep a folder of **surprising, important, hard-won insights** in [`lessons-learned/`](lessons-learned/INDEX.md).

- **Decision Diary vs. Lessons Learned:**
  - **Decisions** record *intentional choices and trade-offs* we made.
  - **Lessons Learned** record *things that surprised us and are important to remember* for future work.

### When to Record a Lesson (Proactive)
Create a new lesson file whenever you encounter something non-obvious that could easily trip up another agent or developer, such as:
- Unexpected dataset quirks (coordinate conventions like planetocentric vs. planetographic latitudes, `-180..180` vs. `0..360` longitudes, nodata sentinels, unit mismatches, projection distortion).
- Library, browser, build-tool, or API surprises and subtle failure modes.
- Scientific/domain caveats or edge cases in scoring/extrapolation that weren't obvious upfront.
- False assumptions that cost significant debugging time, plus the verified fix.

### When NOT to Record a Lesson
Do **not** create lesson files for typos, standard syntax errors, missing imports, or routine debugging steps.

### File Naming & Index Rules
1. Create one Markdown file per lesson at `lessons-learned/YYYY-MM-DD-<short-slug>.md` (use the current date and a descriptive kebab-case slug).
2. Follow the template in [`lessons-learned/INDEX.md`](lessons-learned/INDEX.md) (`Date`, `Area / Tags`, `What Surprised Us`, `Why It Matters`, `Rule of Thumb / What To Do Instead`, `References`).
3. **Always** add a row for the new file to the index table in [`lessons-learned/INDEX.md`](lessons-learned/INDEX.md).

---

## 4. Core Engineering & Scientific Guardrails

All code changes must uphold the following rules from [`REQUIREMENTS.md`](REQUIREMENTS.md):

1. **Unit TDD (`ER-1`) & Coverage (`ER-2`):** Write failing unit tests before implementing core logic (ETL aggregators, pluggable dimension scorers, normalization/distance functions, divergence explainer, API handlers). Target **~80% unit test coverage**.
2. **Modularity & SOLID Design (`ER-4`):** Keep the ETL pipeline, scoring engine, API layer, and frontend UI cleanly decoupled. Consult and follow [`.agents/skills/solid-principles/SKILL.md`](.agents/skills/solid-principles/SKILL.md) when designing new modules/classes or refactoring non-trivial code.
3. **Offline Heavy ETL / Thin Client (`DR-2`):** Never download or parse raw geospatial rasters (GeoTIFF, NetCDF, HDF5) in the browser. Pre-process into lightweight JSON/GeoJSON or vector tiles offline.
4. **Full Data Provenance (`DR-3`):** Every metric in the spatial index and target catalog must carry metadata for **source agency/mission**, **dataset name**, **reference/portal URL**, **physical unit**, and **spatial/temporal resolution**.
5. **Scientific Transparency (`FR-3`, `FR-10`, `FR-11`):**
   - Explicitly flag interpolated or extrapolated planetary target parameters.
   - Guard against all-zero weights and return `N/A` for dimensions whose parameters are all disabled.
   - Surface Earth-limit caveats (gravity, vacuum/atmosphere, radiation) alongside similarity breakdowns.
6. **Deterministic Test Fixtures (`DR-4`):** Use small, deterministic synthetic/sampled fixtures for unit and integration tests—tests must not require downloading full global datasets.
7. **Verification Honesty:** Only report tests, builds, or coverage numbers as passing if you actually ran them after your final edit and observed all reported checks pass.
