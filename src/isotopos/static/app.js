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
  highlightSelectedSiteOnMap,
  initEarthMap,
  populateLayerSwitcher,
  resizeEarthMap,
  startAutoSpinLoop,
  updateEarthMapLayers,
  updateLegendGradient,
} from "./js/components/globe_map.js";
import { initStarfield } from "./js/components/starfield.js";
import {
  bindTargetPanelEvents,
  populatePresetDropdown,
  syncControlsFromTarget,
} from "./js/components/target_panel.js";
import { state } from "./js/state.js";
import { MenuCollapseController, SidebarController } from "./js/ui/collapsible.js";
import { setButtonPressed } from "./js/ui/dom.js";
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

function scheduleRank() {
  clearTimeout(state.rankDebounce);
  state.rankDebounce = setTimeout(runRank, 110);
}

function handleSelectRankedSite(result) {
  state.userInteracting = true;
  clearTimeout(state.flyToTimer);
  showBreakdown(result, { collapseCtrl, onSelectSite: handleSelectRankedSite });
  state.map?.flyTo({ center: [result.site.lon, result.site.lat], zoom: 4.5 });
  state.flyToTimer = setTimeout(() => {
    if (!state.pointerDown) state.userInteracting = false;
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
  const seq = ++state.rankSeq;
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
  if (seq !== state.rankSeq) return;
  state.lastRankResponse = data;

  const dt = Math.round(performance.now() - t0);
  document.getElementById("eval-timing").textContent =
    `${data.filtered_h3_count.toLocaleString()} cells • ${dt} ms`;
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
    highlightSelectedSiteOnMap("");
    document.getElementById("breakdown-card").classList.add("hidden");
  }
}

async function selectPreset(presetId) {
  if (!presetId || presetId === "__custom__") return;
  const target = await extractTarget({ preset_id: presetId });
  state.target = target;
  state.activePresetId = presetId;
  state.targetCustomized = false;
  state.weights = { ...(target.recommended_weights || {}) };
  document.getElementById("preset-select").value = presetId;
  document.getElementById("preset-context").textContent =
    `${target.mission_context || ""} — ${target.notes || ""}`;
  syncControlsFromTarget({ onSyncSummaries: syncMenuSummaries });
  await runRank();
}

async function extractCoordinate(lat, lon) {
  const target = await extractTarget({ body: state.body, lat, lon });
  state.target = target;
  state.activePresetId = null;
  state.targetCustomized = false;
  document.getElementById("preset-select").value = "__custom__";
  document.getElementById("preset-context").textContent = target.notes || "";
  syncControlsFromTarget({ onSyncSummaries: syncMenuSummaries });
  await runRank();
}

function bindUIEvents() {
  const simpleBtn = document.getElementById("btn-mode-simple");
  const advancedBtn = document.getElementById("btn-mode-advanced");

  simpleBtn?.addEventListener("click", () => {
    state.mode = "simple";
    setButtonPressed(simpleBtn, true);
    setButtonPressed(advancedBtn, false);
    document.getElementById("advanced-controls").classList.add("hidden");
  });

  advancedBtn?.addEventListener("click", () => {
    state.mode = "advanced";
    setButtonPressed(advancedBtn, true);
    setButtonPressed(simpleBtn, false);
    document.getElementById("advanced-controls").classList.remove("hidden");
    syncControlsFromTarget({ onSyncSummaries: syncMenuSummaries });
  });

  document.getElementById("chk-novel-only").addEventListener("change", (e) => {
    state.excludeWellKnown = e.target.checked;
    runRank();
  });

  document.getElementById("btn-toggle-spin").addEventListener("click", (e) => {
    state.autoSpin = !state.autoSpin;
    e.target.textContent = state.autoSpin ? "Auto-Spin: ON" : "Auto-Spin: OFF";
    e.target.setAttribute("aria-pressed", state.autoSpin ? "true" : "false");
  });

  document.getElementById("btn-toggle-projection").addEventListener("click", (e) => {
    state.isGlobe = !state.isGlobe;
    state.map?.setProjection({ type: state.isGlobe ? "globe" : "mercator" });
    e.target.textContent = state.isGlobe ? "3D Globe: ON" : "2D Map: ON";
    e.target.setAttribute("aria-pressed", state.isGlobe ? "true" : "false");
  });

  bindTargetPanelEvents({
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

  const tabHotspots = document.getElementById("tab-hotspots");
  const tabH3 = document.getElementById("tab-h3");

  tabHotspots?.addEventListener("click", () => {
    state.activeTab = "hotspots";
    setButtonPressed(tabHotspots, true);
    setButtonPressed(tabH3, false);
    renderRankedList({ onSelectSite: handleSelectRankedSite });
  });

  tabH3?.addEventListener("click", () => {
    state.activeTab = "h3";
    setButtonPressed(tabH3, true);
    setButtonPressed(tabHotspots, false);
    renderRankedList({ onSelectSite: handleSelectRankedSite });
  });

  document.getElementById("btn-evaluate-weights")?.addEventListener("click", () => {
    evaluateMissionWeights({
      onWeightsApplied: async () => {
        syncControlsFromTarget({ onSyncSummaries: syncMenuSummaries });
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
