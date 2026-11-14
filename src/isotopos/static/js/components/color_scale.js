// Scientific color palette scaling, legend formatting, and MapLibre paint expression builders

import { PALETTES, state } from "../state.js";

export function formatLegendTick(val, isRaw) {
  if (isRaw) {
    return Math.abs(val) >= 100 ? String(Math.round(val)) : val.toFixed(1);
  }
  return `${Math.round(val)}%`;
}

export function updateLegendGradient() {
  const bar = document.getElementById("legend-gradient-bar");
  if (!bar) return;
  const stops = PALETTES[state.palette] || PALETTES.bioluminescent;
  const cssStops = stops.map(([t, col]) => `${col} ${Math.round(t * 100)}%`).join(", ");
  bar.style.background = `linear-gradient(90deg, ${cssStops})`;
}

export function computeLayerColorRange({
  features,
  cellDisplayValues,
  isScoreLayer,
  effectiveCutoff,
  scaleMode,
  paramSpec,
}) {
  let dataMin = Infinity;
  let dataMax = -Infinity;
  let validCount = 0;

  for (const feat of features) {
    const v = cellDisplayValues[feat.properties.id] ?? -999999;
    if (v <= -99999) continue;
    if (isScoreLayer && v < effectiveCutoff) continue;
    validCount += 1;
    if (v < dataMin) dataMin = v;
    if (v > dataMax) dataMax = v;
  }

  let minVal = 0;
  let maxVal = 100;
  if (!isScoreLayer && paramSpec) {
    if (scaleMode === "auto" && validCount > 0) {
      minVal = dataMin;
      maxVal = dataMax;
    } else {
      minVal = paramSpec.earth_min;
      maxVal = paramSpec.earth_max;
    }
  } else if (scaleMode === "auto" && validCount > 0) {
    minVal = dataMin;
    maxVal = dataMax;
  }

  if (!Number.isFinite(minVal) || !Number.isFinite(maxVal)) {
    minVal = 0;
    maxVal = 100;
  }
  if (maxVal - minVal < (isScoreLayer ? 2.0 : 1e-3)) {
    const pad = isScoreLayer ? 1.0 : Math.max(0.05, Math.abs(minVal) * 0.05);
    minVal = isScoreLayer ? Math.max(0, minVal - pad) : minVal - pad;
    maxVal = isScoreLayer ? Math.min(100, maxVal + pad) : maxVal + pad;
  }

  return { minVal, maxVal, validCount };
}

export function updateLegendLabels({ legendTitle, minVal, maxVal, isScoreLayer }) {
  const isRaw = !isScoreLayer;
  const minLabel = formatLegendTick(minVal, isRaw);
  const maxLabel = formatLegendTick(maxVal, isRaw);
  const midLabel = formatLegendTick((minVal + maxVal) / 2, isRaw);

  const titleEl = document.getElementById("legend-title");
  const minEl = document.getElementById("legend-min");
  const midEl = document.getElementById("legend-mid");
  const maxEl = document.getElementById("legend-max");
  const summaryEl = document.getElementById("summary-legend");

  if (titleEl) titleEl.textContent = legendTitle;
  if (minEl) minEl.textContent = minLabel;
  if (midEl) midEl.textContent = midLabel;
  if (maxEl) maxEl.textContent = maxLabel;
  if (summaryEl) summaryEl.textContent = `${minLabel}–${maxLabel}`;
}

export function buildFillColorExpression({ valExpr, effectiveCutoff, paletteStops, minVal, maxVal }) {
  return [
    "case",
    ["<", valExpr, effectiveCutoff],
    "rgba(15, 23, 42, 0.0)",
    [
      "interpolate",
      ["linear"],
      valExpr,
      ...paletteStops.flatMap(([t, col]) => [minVal + t * (maxVal - minVal), col]),
    ],
  ];
}

export function buildFillOpacityExpression({
  valExpr,
  isScoreLayer,
  effectiveCutoff,
  hexOpacity,
  minVal,
  maxVal,
}) {
  if (!isScoreLayer) {
    return [
      "case",
      ["<=", valExpr, -99999],
      0.0,
      Number((hexOpacity * 0.88).toFixed(3)),
    ];
  }

  const span = Math.max(1e-6, maxVal - minVal);
  const sLow = minVal;
  const sMid = minVal + 0.45 * span;
  const sHigh = minVal + 0.78 * span;

  return [
    "case",
    ["<", valExpr, effectiveCutoff],
    0.0,
    [
      "interpolate",
      ["linear"],
      valExpr,
      sLow,
      Number((hexOpacity * 0.44).toFixed(3)),
      sMid,
      Number((hexOpacity * 0.74).toFixed(3)),
      sHigh,
      Number((hexOpacity * 0.95).toFixed(3)),
      maxVal,
      Number(hexOpacity.toFixed(3)),
    ],
  ];
}

export function buildOutlineOpacityExpression({ valExpr, effectiveCutoff }) {
  return [
    "case",
    ["<", valExpr, effectiveCutoff],
    0.0,
    ["interpolate", ["linear"], ["zoom"], 2.2, 0.0, 3.3, 0.18, 5.2, 0.45],
  ];
}
