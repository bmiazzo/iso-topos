// iso-topos Dual-Mode 3D Globe Scientist UI — Composition Root

import {
  extractTarget,
  fetchEarthGrid,
  fetchMetadata,
  inspectSite,
  rankAnalogs,
} from "./js/api.js";
import {
  bindAdvancedEvents,
  buildActiveFilters,
  buildAdvancedControls,
} from "./js/components/advanced_panel.js";
import { evaluateMissionWeights } from "./js/components/ai_weights.js";
import {
  renderRankedList,
  resizeDimensionChart,
  showBreakdown,
} from "./js/components/breakdown_panel.js";
import {
  applyBasemap,
  initEarthMap,
  initStarfield,
  populateLayerSwitcher,
  resizeEarthMap,
  startAutoSpinLoop,
  updateEarthMapLayers,
  updateLegendGradient,
} from "./js/components/globe_map.js";
import {
  bindPlanetaryPickerEvents,
  drawPlanetaryPicker,
} from "./js/components/planetary_picker.js";
import { state } from "./js/state.js";
import { MenuCollapseController, SidebarController } from "./js/ui/collapsible.js";
import { updateAllMenuSummaries } from "./js/ui/menu_summaries.js";

const collapseCtrl = new MenuCollapseController();
const sidebarCtrl = new SidebarController({
  workspaceEl: document.getElementById("workspace"),
  collapseLeftBtn: document.getElementById("btn-collapse-left"),
  collapseRightBtn: document.getElementById("btn-collapse-right"),
  expandLeftBtn: document.getElementById("btn-expand-left"),
  expandRightBtn: document.getElementById("btn-expand-right"),
  onLayoutChange: () => {
    resizeEarthMap();
    resizeDimensionChart();
  },
});

function syncMenuSummaries() {
  updateAllMenuSummaries(collapseCtrl, buildActiveFilters().length);
}

function populatePresetDropdown() {
  const sel = document.getElementById("preset-select");
  if (!sel) return;
  sel.innerHTML = "";
  const bodyPresets = state.metadata.presets.filter((p) => p.body === state.body);
  for (const p of bodyPresets) {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = `${p.name} (${p.lat.toFixed(1)}°, ${p.lon.toFixed(1)}°E)`;
    sel.appendChild(opt);
  }
  const customOpt = document.createElement("option");
  customOpt.value = "__custom__";
  customOpt.textContent = "— Custom Planetary Coordinate —";
  customOpt.disabled = true;
  sel.appendChild(customOpt);
}

function syncControlsFromTarget() {
  if (!state.target) return;
  document.getElementById("input-lat").value = state.target.lat.toFixed(2);
  document.getElementById("input-lon").value = state.target.lon.toFixed(2);

  const badge = document.getElementById("extrapolation-badge");
  if (state.target.is_extrapolated) {
    badge.textContent = "Extrapolated Target";
    badge.className = "badge badge-warn";
  } else {
    badge.textContent = "Preset Exact";
    badge.className = "badge badge-neutral";
  }

  for (const p of state.metadata.parameters) {
    const valInput = document.getElementById(`val-${p.id}`);
    const wtSlider = document.getElementById(`wt-${p.id}`);
    const wtLabel = document.getElementById(`wt-lbl-${p.id}`);
    const chkEnable = document.getElementById(`chk-en-${p.id}`);
    if (valInput) valInput.value = state.target.parameters[p.id];
    const wPct = Math.round((state.weights[p.id] ?? p.default_weight) * 100);
    if (wtSlider) wtSlider.value = String(wPct);
    if (wtLabel) wtLabel.textContent = `${wPct}%`;
    if (chkEnable) chkEnable.checked = wPct > 0;
  }

  drawPlanetaryPicker();
  syncMenuSummaries();
}

function scheduleRank() {
  clearTimeout(state.rankDebounce);
  state.rankDebounce = setTimeout(runRank, 110);
}

function handleSelectRankedSite(result) {
  state.userInteracting = true;
  showBreakdown(result, { collapseCtrl, onSelectSite: handleSelectRankedSite });
  state.map?.flyTo({ center: [result.site.lon, result.site.lat], zoom: 4.5 });
  setTimeout(() => {
    state.userInteracting = false;
  }, 2500);
}

async function inspectAnySiteById(siteId) {
  if (!state.target || !siteId) return;
  const cached = [
    ...(state.lastRankResponse?.hotspot_results || []),
    ...(state.lastRankResponse?.top_h3_results || []),
  ].find((r) => r.site.id === siteId);
  if (cached) {
    showBreakdown(cached, { collapseCtrl, onSelectSite: handleSelectRankedSite });
    return;
  }

  const result = await inspectSite(siteId, {
    target: state.target,
    weights: state.weights,
    mode: state.scoringMode,
  });
  if (result) {
    showBreakdown(result, { collapseCtrl, onSelectSite: handleSelectRankedSite });
  }
}

async function runRank() {
  if (!state.target) return;
  const t0 = performance.now();
  const activeDimId = state.activeLayer.startsWith("dim:") ? state.activeLayer.slice(4) : null;

  const data = await rankAnalogs({
    target: state.target,
    weights: state.weights,
    mode: state.scoringMode,
    filters: buildActiveFilters(),
    exclude_well_known: state.excludeWellKnown,
    top_k: 15,
    dimension_id: activeDimId,
  });
  state.lastRankResponse = data;

  const dt = Math.round(performance.now() - t0);
  document.getElementById("eval-timing").textContent = `${data.filtered_h3_count.toLocaleString()} cells • ${dt} ms`;
  document.getElementById("all-zero-warning").classList.toggle("hidden", !data.all_weights_zero);

  await updateEarthMapLayers(true);
  renderRankedList({ onSelectSite: handleSelectRankedSite });
  syncMenuSummaries();

  const defaultPool = state.activeTab === "hotspots" ? data.hotspot_results : data.top_h3_results;
  const existing = [...data.hotspot_results, ...data.top_h3_results].find(
    (r) => r.site.id === state.selectedSiteId
  );
  if (existing) {
    showBreakdown(existing, { collapseCtrl, onSelectSite: handleSelectRankedSite });
  } else if (state.selectedSiteId && state.selectedSiteId in (data.cell_scores || {})) {
    await inspectAnySiteById(state.selectedSiteId);
  } else if (defaultPool.length > 0) {
    showBreakdown(defaultPool[0], { collapseCtrl, onSelectSite: handleSelectRankedSite });
  } else {
    state.selectedSiteId = null;
    document.getElementById("breakdown-card").classList.add("hidden");
  }
}

async function selectPreset(presetId) {
  if (!presetId || presetId === "__custom__") return;
  const target = await extractTarget({ preset_id: presetId });
  state.target = target;
  state.activePresetId = presetId;
  state.weights = { ...(target.recommended_weights || {}) };
  document.getElementById("preset-select").value = presetId;
  document.getElementById("preset-context").textContent =
    `${target.mission_context || ""} — ${target.notes || ""}`;
  syncControlsFromTarget();
  await runRank();
}

async function extractCoordinate(lat, lon) {
  const target = await extractTarget({ body: state.body, lat, lon });
  state.target = target;
  state.activePresetId = null;
  document.getElementById("preset-select").value = "__custom__";
  document.getElementById("preset-context").textContent = target.notes || "";
  syncControlsFromTarget();
  await runRank();
}

function bindUIEvents() {
  document.getElementById("btn-body-moon").addEventListener("click", async () => {
    state.body = "moon";
    document.getElementById("btn-body-moon").classList.add("active");
    document.getElementById("btn-body-mars").classList.remove("active");
    populatePresetDropdown();
    const first = state.metadata.presets.find((p) => p.body === "moon");
    if (first) await selectPreset(first.id);
  });

  document.getElementById("btn-body-mars").addEventListener("click", async () => {
    state.body = "mars";
    document.getElementById("btn-body-mars").classList.add("active");
    document.getElementById("btn-body-moon").classList.remove("active");
    populatePresetDropdown();
    const first = state.metadata.presets.find((p) => p.body === "mars");
    if (first) await selectPreset(first.id);
  });

  document.getElementById("btn-mode-simple").addEventListener("click", () => {
    state.mode = "simple";
    document.getElementById("btn-mode-simple").classList.add("active");
    document.getElementById("btn-mode-advanced").classList.remove("active");
    document.getElementById("advanced-controls").classList.add("hidden");
  });

  document.getElementById("btn-mode-advanced").addEventListener("click", () => {
    state.mode = "advanced";
    document.getElementById("btn-mode-advanced").classList.add("active");
    document.getElementById("btn-mode-simple").classList.remove("active");
    document.getElementById("advanced-controls").classList.remove("hidden");
    syncControlsFromTarget();
  });

  document.getElementById("chk-novel-only").addEventListener("change", (e) => {
    state.excludeWellKnown = e.target.checked;
    runRank();
  });

  document.getElementById("btn-toggle-spin").addEventListener("click", (e) => {
    state.autoSpin = !state.autoSpin;
    e.target.textContent = state.autoSpin ? "Auto-Spin: ON" : "Auto-Spin: OFF";
  });

  document.getElementById("btn-toggle-projection").addEventListener("click", (e) => {
    state.isGlobe = !state.isGlobe;
    state.map?.setProjection({ type: state.isGlobe ? "globe" : "mercator" });
    e.target.textContent = state.isGlobe ? "3D Globe: ON" : "2D Map: ON";
  });

  document.getElementById("preset-select").addEventListener("change", (e) => {
    selectPreset(e.target.value);
  });

  bindPlanetaryPickerEvents({
    onSelectPreset: selectPreset,
    onExtractCoordinate: extractCoordinate,
  });

  bindAdvancedEvents({
    onRank: runRank,
    onScheduleRank: scheduleRank,
    onSyncSummaries: syncMenuSummaries,
  });

  document.getElementById("layer-variable-select").addEventListener("change", async (e) => {
    state.activeLayer = e.target.value;
    syncMenuSummaries();
    if (state.activeLayer.startsWith("dim:")) {
      await runRank();
    } else {
      await updateEarthMapLayers(true);
    }
  });

  document.getElementById("palette-select").addEventListener("change", (e) => {
    state.palette = e.target.value;
    syncMenuSummaries();
    updateLegendGradient();
    updateEarthMapLayers(false);
  });

  document.getElementById("scale-mode-select").addEventListener("change", (e) => {
    state.scaleMode = e.target.value;
    updateEarthMapLayers(false);
  });

  document.getElementById("basemap-select").addEventListener("change", (e) => {
    applyBasemap(e.target.value);
  });

  document.getElementById("hex-opacity").addEventListener("input", (e) => {
    state.hexOpacity = parseFloat(e.target.value);
    document.getElementById("hex-opacity-lbl").textContent = `${Math.round(state.hexOpacity * 100)}%`;
    updateEarthMapLayers(false);
  });

  document.getElementById("min-score-filter").addEventListener("input", (e) => {
    state.minScoreFilter = parseInt(e.target.value, 10) || 0;
    document.getElementById("min-score-lbl").textContent = `${state.minScoreFilter}%`;
    updateEarthMapLayers(false);
  });

  document.getElementById("chk-show-hotspots").addEventListener("change", (e) => {
    state.showHotspots = e.target.checked;
    updateEarthMapLayers(false);
  });

  document.getElementById("tab-hotspots").addEventListener("click", () => {
    state.activeTab = "hotspots";
    document.getElementById("tab-hotspots").classList.add("active");
    document.getElementById("tab-h3").classList.remove("active");
    renderRankedList({ onSelectSite: handleSelectRankedSite });
  });

  document.getElementById("tab-h3").addEventListener("click", () => {
    state.activeTab = "h3";
    document.getElementById("tab-h3").classList.add("active");
    document.getElementById("tab-hotspots").classList.remove("active");
    renderRankedList({ onSelectSite: handleSelectRankedSite });
  });

  document.getElementById("btn-evaluate-weights")?.addEventListener("click", () => {
    evaluateMissionWeights({
      onWeightsApplied: async () => {
        syncControlsFromTarget();
        await runRank();
      },
      onSyncSummaries: syncMenuSummaries,
    });
  });
}

async function init() {
  initStarfield();
  sidebarCtrl.init();
  collapseCtrl.registerContainer(document);
  collapseCtrl.onToggle("detail-chart", (isOpen) => {
    if (isOpen) requestAnimationFrame(() => resizeDimensionChart());
  });
  collapseCtrl.onToggle("site-breakdown", (isOpen) => {
    if (isOpen) requestAnimationFrame(() => resizeDimensionChart());
  });

  const [meta, geo] = await Promise.all([fetchMetadata(), fetchEarthGrid()]);
  state.metadata = meta;
  state.earthGeojson = geo;

  populateLayerSwitcher();
  populatePresetDropdown();
  buildAdvancedControls({
    collapseCtrl,
    onScheduleRank: scheduleRank,
    onSyncSummaries: syncMenuSummaries,
  });
  updateLegendGradient();
  initEarthMap({ onInspectSite: inspectAnySiteById });
  bindUIEvents();
  startAutoSpinLoop();

  const firstPreset = state.metadata.presets.find((p) => p.body === state.body);
  if (firstPreset) {
    await selectPreset(firstPreset.id);
  }
}

init();
