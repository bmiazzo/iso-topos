// Live summary pill synchronizer for all collapsible menu headers

import { state } from "../state.js";

const PALETTE_SHORT_NAMES = {
  bioluminescent: "Biolum",
  viridis: "Viridis",
  magma: "Magma",
  plasma: "Plasma",
  turbo: "Turbo",
};

export function updateAllMenuSummaries(collapseCtrl, activeFilterCount = 0) {
  if (!collapseCtrl || !state.metadata) return;

  // Target Selection & Planetary Map Picker
  if (state.activePresetId) {
    const preset = state.metadata.presets.find((p) => p.id === state.activePresetId);
    collapseCtrl.setSummary("summary-target", preset ? preset.name : "Preset", "accent");
  } else if (state.target) {
    collapseCtrl.setSummary("summary-target", "Custom Coord", "warn");
  } else {
    collapseCtrl.setSummary("summary-target", "None", "neutral");
  }

  if (state.target) {
    const coord = `${state.target.lat.toFixed(1)}°, ${state.target.lon.toFixed(1)}°`;
    const tag = state.target.is_extrapolated ? "Extrap." : "Exact";
    collapseCtrl.setSummary(
      "summary-picker",
      `${coord} • ${tag}`,
      state.target.is_extrapolated ? "warn" : "neutral"
    );
  }

  // AI Evaluator
  const aiVariant =
    state.aiWeightStatus === "Applied"
      ? "ok"
      : state.aiWeightStatus === "Error"
      ? "warn"
      : state.aiWeightStatus === "Evaluating..."
      ? "accent"
      : "neutral";
  collapseCtrl.setSummary("summary-ai", state.aiWeightStatus, aiVariant);

  // Advanced Scoring Mode & Filters
  collapseCtrl.setSummary(
    "summary-scoring",
    state.scoringMode === "strict" ? "Strict" : "Clamped",
    state.scoringMode === "strict" ? "warn" : "accent"
  );
  collapseCtrl.setSummary(
    "summary-filters",
    activeFilterCount > 0 ? `${activeFilterCount} active` : "None",
    activeFilterCount > 0 ? "accent" : "neutral"
  );

  // Parameter Weights (overall & per-dimension)
  const params = state.metadata.parameters || [];
  let totalActive = 0;
  for (const dim of state.metadata.dimensions || []) {
    const dimParams = params.filter((p) => p.dimension_id === dim.id);
    let dimActive = 0;
    let dimWeightSum = 0;
    for (const p of dimParams) {
      const w = state.weights[p.id] ?? p.default_weight ?? 0;
      if (w > 0) {
        dimActive += 1;
        totalActive += 1;
        dimWeightSum += w;
      }
    }
    const avgPct = dimActive > 0 ? Math.round((dimWeightSum / dimActive) * 100) : 0;
    collapseCtrl.setSummary(
      `summary-dim-${dim.id}`,
      `${dimActive}/${dimParams.length} • ${avgPct}%`,
      dimActive === 0 ? "neutral" : "ok"
    );
  }
  collapseCtrl.setSummary(
    "summary-weights",
    `${totalActive}/${params.length} active`,
    totalActive === 0 ? "warn" : "ok"
  );

  // Globe Layers Overlay
  let layerShort = "Overall";
  if (state.activeLayer.startsWith("dim:")) {
    const dimId = state.activeLayer.slice(4);
    const dim = state.metadata.dimensions.find((d) => d.id === dimId);
    layerShort = dim ? dim.name.split(" ")[0] : dimId;
  } else if (state.activeLayer.startsWith("raw:")) {
    const pId = state.activeLayer.slice(4);
    const param = params.find((p) => p.id === pId);
    layerShort = param ? param.label.split(" ")[0] : pId;
  }
  const palShort = PALETTE_SHORT_NAMES[state.palette] || state.palette;
  collapseCtrl.setSummary("summary-layers", `${layerShort} • ${palShort}`, "accent");
}
