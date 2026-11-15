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
  getActiveTabPool,
  renderRankedList,
  resizeDimensionChart,
  showBreakdown,
} from "./js/components/breakdown_panel.js";
import {
  applyBasemap,
  flyToSiteOnGlobe,
  highlightSelectedSiteOnMap,
  initEarthMap,
  populateLayerSwitcher,
  requestAutoSpinFrame,
  resetEarthGlobeView,
  resizeEarthMap,
  setEarthProjection,
  startAutoSpinLoop,
  updateEarthHexOpacity,
  updateEarthMapLayers,
  updateLegendGradient,
  zoomEarthGlobe,
} from "./js/components/globe_map.js";
import { initStarfield } from "./js/components/starfield.js";
import {
  bindTargetPanelEvents,
  populatePresetDropdown,
  syncControlsFromTarget,
} from "./js/components/target_panel.js";
import { state } from "./js/state.js";
import { MenuCollapseController, SidebarController } from "./js/ui/collapsible.js";
import { prefersReducedMotion, setButtonPressed, setSpinButtonState } from "./js/ui/dom.js";
import { updateAllMenuSummaries } from "./js/ui/menu_summaries.js";
import {
  MenuResizeController,
  OverlayResizeController,
  SidebarResizeController,
} from "./js/ui/resizable.js";

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

const sidebarResizeCtrl = new SidebarResizeController({
  workspaceEl: document.getElementById("workspace"),
  onLayoutChange: () => {
    resizeEarthMap();
    resizeDimensionChart();
  },
  specs: [
    {
      key: "left",
      handleEl: document.getElementById("resizer-left"),
      side: "left",
      cssVar: "--left-width",
      defaultWidth: 340,
      minWidth: 240,
      maxWidth: 640,
      minCenterWidth: 260,
      oppositeCssVar: "--right-width",
      oppositeDefault: 460,
      oppositeCollapsedClass: "right-collapsed",
    },
    {
      key: "right",
      handleEl: document.getElementById("resizer-right"),
      side: "right",
      cssVar: "--right-width",
      defaultWidth: 460,
      minWidth: 280,
      maxWidth: 820,
      minCenterWidth: 260,
      oppositeCssVar: "--left-width",
      oppositeDefault: 340,
      oppositeCollapsedClass: "left-collapsed",
    },
  ],
});

const menuResizeCtrl = new MenuResizeController({
  onMenuResize: (id) => {
    if (id === "detail-chart" || id === "site-breakdown") {
      requestAnimationFrame(() => resizeDimensionChart());
    }
  },
});

const overlayResizeCtrl = new OverlayResizeController({
  stageEl: document.getElementById("main-stage"),
});

function syncMenuSummaries() {
  updateAllMenuSummaries(collapseCtrl, buildActiveFilters().length);
}

function scheduleRank() {
  clearTimeout(state.rankDebounce);
  state.rankDebounce = setTimeout(() => runRank({ flyToTop: false }), 110);
}

function setRightDrawerView(mode) {
  state.rightViewMode = mode;
  const splitBtn = document.getElementById("btn-right-view-split");
  const inspBtn = document.getElementById("btn-right-view-inspector");
  const candBtn = document.getElementById("btn-right-view-candidates");
  setButtonPressed(splitBtn, mode === "split");
  setButtonPressed(inspBtn, mode === "inspector");
  setButtonPressed(candBtn, mode === "candidates");

  const rankedSec = document.getElementById("ranked-analogs-section");
  const breakdownSec = document.getElementById("breakdown-card");
  if (rankedSec) {
    rankedSec.classList.toggle("hidden", mode === "inspector");
  }
  if (breakdownSec && state.selectedSiteId) {
    breakdownSec.classList.toggle("hidden", mode === "candidates");
  }
  requestAnimationFrame(() => resizeDimensionChart());
}

function handleSelectRankedSite(result) {
  if (state.rightViewMode === "candidates") {
    setRightDrawerView("inspector");
  }
  showBreakdown(result, { collapseCtrl, onSelectSite: handleSelectRankedSite });
  flyToSiteOnGlobe(result.site.lon, result.site.lat, 4.3, true);
}

async function inspectAnySiteById(siteId) {
  if (!state.target || !siteId) return;
  if (state.rightViewMode === "candidates") {
    setRightDrawerView("inspector");
  }
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

function updateNoveltyPill(data) {
  const pill = document.getElementById("novel-status-pill");
  if (!pill) return;
  if (!state.excludeWellKnown) {
    pill.classList.add("hidden");
    return;
  }
  const h3Excl = data.excluded_well_known_h3_count || 0;
  const hsExcl = data.excluded_well_known_hotspot_count || 0;
  pill.textContent = `${h3Excl.toLocaleString()} cells · ${hsExcl} sites excluded`;
  pill.className = "summary-pill pill-warn";
  pill.classList.remove("hidden");
}

async function runRank({ flyToTop = false } = {}) {
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
    `${data.filtered_h3_count.toLocaleString()} cells · ${dt} ms`;
  document.getElementById("all-zero-warning").classList.toggle("hidden", !data.all_weights_zero);
  updateNoveltyPill(data);

  await updateEarthMapLayers(true);
  renderRankedList({ onSelectSite: handleSelectRankedSite });
  syncMenuSummaries();

  const defaultPool = getActiveTabPool(data, state.activeTab);
  const existing = [
    ...(data.hotspot_results || []),
    ...(data.top_h3_results || []),
  ].find((r) => r.site.id === state.selectedSiteId);

  if (flyToTop && defaultPool.length > 0) {
    showBreakdown(defaultPool[0], { collapseCtrl, onSelectSite: handleSelectRankedSite });
    flyToSiteOnGlobe(defaultPool[0].site.lon, defaultPool[0].site.lat, 3.0, true);
  } else if (existing) {
    showBreakdown(existing, { collapseCtrl, onSelectSite: handleSelectRankedSite });
  } else if (state.selectedSiteId && state.selectedSiteId in (data.cell_scores || {})) {
    await inspectAnySiteById(state.selectedSiteId);
  } else if (defaultPool.length > 0) {
    showBreakdown(defaultPool[0], { collapseCtrl, onSelectSite: handleSelectRankedSite });
    if (state.excludeWellKnown) {
      flyToSiteOnGlobe(defaultPool[0].site.lon, defaultPool[0].site.lat, 3.0, false);
    }
  } else {
    state.selectedSiteId = null;
    highlightSelectedSiteOnMap("");
    document.getElementById("breakdown-card").classList.add("hidden");
  }
}

async function selectPreset(presetId) {
  if (!presetId || presetId === "__custom__") return;
  const target = await extractTarget({ preset_id: presetId });
  state.body = target.body;
  setButtonPressed(document.getElementById("btn-body-moon"), target.body === "moon");
  setButtonPressed(document.getElementById("btn-body-mars"), target.body === "mars");
  populatePresetDropdown();

  state.target = target;
  state.activePresetId = presetId;
  state.targetCustomized = false;
  state.weights = { ...(target.recommended_weights || {}) };
  document.getElementById("preset-select").value = presetId;
  document.getElementById("preset-context").textContent =
    `${target.mission_context || ""} — ${target.notes || ""}`;
  syncControlsFromTarget({ onSyncSummaries: syncMenuSummaries });
  await runRank({ flyToTop: true });
}

async function extractCoordinate(lat, lon) {
  const target = await extractTarget({ body: state.body, lat, lon });
  state.target = target;
  state.activePresetId = null;
  state.targetCustomized = false;
  document.getElementById("preset-select").value = "__custom__";
  document.getElementById("preset-context").textContent = target.notes || "";
  syncControlsFromTarget({ onSyncSummaries: syncMenuSummaries });
  await runRank({ flyToTop: true });
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
    runRank({ flyToTop: false });
  });

  document.getElementById("btn-toggle-spin").addEventListener("click", (e) => {
    state.autoSpin = !state.autoSpin;
    setSpinButtonState(e.target, state.autoSpin);
    requestAutoSpinFrame();
  });

  document.getElementById("btn-toggle-projection").addEventListener("click", (e) => {
    setEarthProjection(!state.isGlobe);
    e.target.textContent = state.isGlobe ? "3D Globe: ON" : "2D Map: ON";
    e.target.setAttribute("aria-pressed", state.isGlobe ? "true" : "false");
  });

  document.getElementById("earth-zoom-in")?.addEventListener("click", () => {
    zoomEarthGlobe(1.55);
  });
  document.getElementById("earth-zoom-out")?.addEventListener("click", () => {
    zoomEarthGlobe(1 / 1.55);
  });
  document.getElementById("earth-zoom-reset")?.addEventListener("click", () => {
    resetEarthGlobeView();
  });

  bindTargetPanelEvents({
    onSelectPreset: selectPreset,
    onExtractCoordinate: extractCoordinate,
  });

  bindAdvancedEvents({
    collapseCtrl,
    onRank: () => runRank({ flyToTop: false }),
    onScheduleRank: scheduleRank,
    onSyncSummaries: syncMenuSummaries,
  });

  const wideRightBtn = document.getElementById("btn-wide-right");
  wideRightBtn?.addEventListener("click", () => {
    const workspaceEl = document.getElementById("workspace");
    if (!workspaceEl) return;
    const nextWide = !workspaceEl.classList.contains("right-wide");
    workspaceEl.classList.toggle("right-wide", nextWide);
    setButtonPressed(wideRightBtn, nextWide);
    wideRightBtn.textContent = nextWide ? "⇔ Standard" : "⇔ Wide";
    sidebarCtrl._runTransitionResizeLoop(260);
  });

  document.getElementById("btn-fly-selected")?.addEventListener("click", () => {
    const site = state.selectedSiteResult?.site;
    if (site) {
      flyToSiteOnGlobe(site.lon, site.lat, 4.2, true);
    }
  });

  document.getElementById("btn-right-view-split")?.addEventListener("click", () => setRightDrawerView("split"));
  document.getElementById("btn-right-view-inspector")?.addEventListener("click", () => setRightDrawerView("inspector"));
  document.getElementById("btn-right-view-candidates")?.addEventListener("click", () => setRightDrawerView("candidates"));

  const btnParamCards = document.getElementById("btn-param-view-cards");
  const btnParamTable = document.getElementById("btn-param-view-table");
  const setParamComparisonView = (view) => {
    setButtonPressed(btnParamCards, view === "cards");
    setButtonPressed(btnParamTable, view === "table");
    document.getElementById("detail-comparison-cards")?.classList.toggle("hidden", view !== "cards");
    document.getElementById("detail-comparison-table-wrap")?.classList.toggle("hidden", view !== "table");
  };
  btnParamCards?.addEventListener("click", () => setParamComparisonView("cards"));
  btnParamTable?.addEventListener("click", () => setParamComparisonView("table"));

  document.getElementById("layer-variable-select").addEventListener("change", async (e) => {
    state.activeLayer = e.target.value;
    syncMenuSummaries();
    if (state.activeLayer.startsWith("dim:")) {
      await runRank({ flyToTop: false });
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
    updateEarthHexOpacity();
  });

  let minScoreRaf = 0;
  document.getElementById("min-score-filter").addEventListener("input", (e) => {
    state.minScoreFilter = parseInt(e.target.value, 10) || 0;
    document.getElementById("min-score-lbl").textContent = `${state.minScoreFilter}%`;
    if (!minScoreRaf) {
      minScoreRaf = requestAnimationFrame(() => {
        minScoreRaf = 0;
        updateEarthMapLayers(false);
      });
    }
  });

  document.getElementById("chk-show-hotspots").addEventListener("change", (e) => {
    state.showHotspots = e.target.checked;
    updateEarthMapLayers(false);
  });

  const tabAll = document.getElementById("tab-all");
  const tabH3 = document.getElementById("tab-h3");
  const tabHotspots = document.getElementById("tab-hotspots");
  const activateTab = (tabKey) => {
    state.activeTab = tabKey;
    setButtonPressed(tabAll, tabKey === "all");
    setButtonPressed(tabH3, tabKey === "h3");
    setButtonPressed(tabHotspots, tabKey === "hotspots");
    renderRankedList({ onSelectSite: handleSelectRankedSite });
  };

  tabAll?.addEventListener("click", () => activateTab("all"));
  tabH3?.addEventListener("click", () => activateTab("h3"));
  tabHotspots?.addEventListener("click", () => activateTab("hotspots"));

  document.getElementById("btn-evaluate-weights")?.addEventListener("click", () => {
    evaluateMissionWeights({
      onWeightsApplied: async () => {
        syncControlsFromTarget({ onSyncSummaries: syncMenuSummaries });
        await runRank({ flyToTop: false });
      },
      onSyncSummaries: syncMenuSummaries,
    });
  });
}

function setLoadingOverlay(text, visible = true) {
  const overlay = document.getElementById("map-loading-overlay");
  const textEl = document.getElementById("map-loading-text");
  if (textEl && text) textEl.textContent = text;
  if (overlay) {
    overlay.classList.toggle("is-hidden", !visible);
  }
}

async function init() {
  initStarfield();
  state.autoSpin = !prefersReducedMotion();
  setSpinButtonState(document.getElementById("btn-toggle-spin"), state.autoSpin);
  sidebarCtrl.init();
  sidebarResizeCtrl.init();
  collapseCtrl.registerContainer(document);
  menuResizeCtrl.registerContainer(document);
  overlayResizeCtrl.registerContainer(document);
  collapseCtrl.onToggle("detail-chart", (isOpen) => {
    if (isOpen) requestAnimationFrame(() => resizeDimensionChart());
  });
  collapseCtrl.onToggle("site-breakdown", (isOpen) => {
    if (isOpen) requestAnimationFrame(() => resizeDimensionChart());
  });

  try {
    setLoadingOverlay("Loading spatial grid & H3 Res 4 cells…", true);
    const [meta, geo] = await Promise.all([fetchMetadata(), fetchEarthGrid()]);
    state.metadata = meta;
    state.earthGeojson = geo;

    setLoadingOverlay("Building 3D globe & computing initial rankings…", true);
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

    // Support URL deep links returned from /planetary (?preset=... or ?body=...&lat=...&lon=...)
    const params = new URLSearchParams(window.location.search);
    const presetParam = params.get("preset");
    const bodyParam = params.get("body");
    const latParam = parseFloat(params.get("lat"));
    const lonParam = parseFloat(params.get("lon"));

    if (presetParam && state.metadata.presets.some((p) => p.id === presetParam)) {
      await selectPreset(presetParam);
      setLoadingOverlay("", false);
      return;
    }

    if ((bodyParam === "moon" || bodyParam === "mars") && !Number.isNaN(latParam) && !Number.isNaN(lonParam)) {
      state.body = bodyParam;
      setButtonPressed(document.getElementById("btn-body-moon"), bodyParam === "moon");
      setButtonPressed(document.getElementById("btn-body-mars"), bodyParam === "mars");
      populatePresetDropdown();
      const first = state.metadata.presets.find((p) => p.body === bodyParam);
      if (first?.recommended_weights) {
        state.weights = { ...first.recommended_weights };
      }
      await extractCoordinate(latParam, lonParam);
      setLoadingOverlay("", false);
      return;
    }

    const firstPreset = state.metadata.presets.find((p) => p.body === state.body);
    if (firstPreset) {
      await selectPreset(firstPreset.id);
    }
    setLoadingOverlay("", false);
  } catch (err) {
    setLoadingOverlay(`Failed to initialize globe: ${err?.message || "Unknown error"}`, true);
    throw err;
  }
}

init();
