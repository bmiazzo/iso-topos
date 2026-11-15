// Scientific color palette scaling, legend formatting, and MapLibre paint expression builders

import { PALETTES, state } from "../state.js";

const LOG_SCALE_K = 50.0;

export function normalizeLon180(lon) {
  return ((((lon + 180) % 360) + 360) % 360) - 180;
}

export function hexToRgb(hex) {
  const clean = hex.replace("#", "");
  return [
    parseInt(clean.slice(0, 2), 16),
    parseInt(clean.slice(2, 4), 16),
    parseInt(clean.slice(4, 6), 16),
  ];
}

export function samplePaletteRgb(stops, tNorm) {
  const t = Math.max(0, Math.min(1, tNorm));
  for (let i = 0; i < stops.length - 1; i++) {
    const [t0, c0] = stops[i];
    const [t1, c1] = stops[i + 1];
    if (t >= t0 && t <= t1) {
      const f = (t - t0) / Math.max(1e-6, t1 - t0);
      const rgb0 = hexToRgb(c0);
      const rgb1 = hexToRgb(c1);
      return [
        Math.round(rgb0[0] + f * (rgb1[0] - rgb0[0])),
        Math.round(rgb0[1] + f * (rgb1[1] - rgb0[1])),
        Math.round(rgb0[2] + f * (rgb1[2] - rgb0[2])),
      ];
    }
  }
  return hexToRgb(stops[stops.length - 1][1]);
}

export function formatLegendTick(val, isRaw) {
  if (isRaw) {
    if (Math.abs(val) >= 100) return String(Math.round(val));
    if (Math.abs(val) >= 10) return val.toFixed(1);
    return val.toFixed(2);
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

function quantile(sorted, q) {
  if (!sorted.length) return 0;
  const pos = (sorted.length - 1) * q;
  const base = Math.floor(pos);
  const rest = pos - base;
  if (sorted[base + 1] !== undefined) {
    return sorted[base] + rest * (sorted[base + 1] - sorted[base]);
  }
  return sorted[base];
}

export function computeLayerColorRange({
  features,
  cellDisplayValues,
  isScoreLayer,
  effectiveCutoff,
  scaleMode,
  paramSpec,
}) {
  const needsQuantiles = scaleMode === "auto";
  const vals = needsQuantiles ? new Float64Array(features.length) : null;
  let validCount = 0;
  let dataMin = Infinity;
  let dataMax = -Infinity;

  for (const feat of features) {
    const v = cellDisplayValues[feat.properties.id] ?? -999999;
    if (v <= -99999) continue;
    if (isScoreLayer && v < effectiveCutoff) continue;
    if (needsQuantiles) vals[validCount] = v;
    validCount += 1;
    if (v < dataMin) dataMin = v;
    if (v > dataMax) dataMax = v;
  }

  let minVal = 0;
  let maxVal = 100;
  let isClipped = false;

  if (scaleMode === "fixed") {
    if (!isScoreLayer && paramSpec) {
      minVal = paramSpec.earth_min;
      maxVal = paramSpec.earth_max;
    } else {
      minVal = 0;
      maxVal = 100;
    }
  } else if (validCount > 0) {
    if (needsQuantiles && validCount >= 16) {
      const sorted = vals.subarray(0, validCount).sort();
      const p2 = quantile(sorted, 0.02);
      const p98 = quantile(sorted, 0.98);
      if (p98 - p2 > (isScoreLayer ? 2.0 : 1e-3)) {
        minVal = p2;
        maxVal = p98;
        isClipped = dataMin < p2 - 1e-5 || dataMax > p98 + 1e-5;
      } else {
        minVal = dataMin;
        maxVal = dataMax;
      }
    } else {
      minVal = dataMin;
      maxVal = dataMax;
    }
  }

  if (!Number.isFinite(minVal) || !Number.isFinite(maxVal)) {
    minVal = 0;
    maxVal = 100;
    dataMin = 0;
    dataMax = 100;
  }

  if (maxVal - minVal < (isScoreLayer ? 2.0 : 1e-3)) {
    const pad = isScoreLayer ? 1.0 : Math.max(0.05, Math.abs(minVal) * 0.05);
    minVal = isScoreLayer ? Math.max(0, minVal - pad) : minVal - pad;
    maxVal = isScoreLayer ? Math.min(100, maxVal + pad) : maxVal + pad;
  }

  const midVal =
    scaleMode === "log"
      ? minVal + ((Math.sqrt(1 + LOG_SCALE_K) - 1) / LOG_SCALE_K) * (maxVal - minVal)
      : (minVal + maxVal) / 2;

  return {
    minVal,
    midVal,
    maxVal,
    rawMin: validCount > 0 ? dataMin : minVal,
    rawMax: validCount > 0 ? dataMax : maxVal,
    isClipped,
    validCount,
  };
}

export function updateLegendLabels({
  legendTitle,
  minVal,
  midVal,
  maxVal,
  rawMin,
  rawMax,
  isClipped,
  isScoreLayer,
  scaleMode,
}) {
  const isRaw = !isScoreLayer;
  const minLabel = formatLegendTick(minVal, isRaw);
  const midLabel = formatLegendTick(midVal ?? (minVal + maxVal) / 2, isRaw);
  const maxLabel = formatLegendTick(maxVal, isRaw);

  const titleEl = document.getElementById("legend-title");
  const minEl = document.getElementById("legend-min");
  const midEl = document.getElementById("legend-mid");
  const maxEl = document.getElementById("legend-max");
  const summaryEl = document.getElementById("summary-legend");
  const boundsEl = document.getElementById("legend-bounds-note");

  if (titleEl) titleEl.textContent = legendTitle;
  if (minEl) minEl.textContent = minLabel;
  if (midEl) midEl.textContent = midLabel;
  if (maxEl) maxEl.textContent = maxLabel;
  if (summaryEl) summaryEl.textContent = `${minLabel}–${maxLabel}`;

  if (boundsEl) {
    if (isClipped && rawMin !== undefined && rawMax !== undefined) {
      boundsEl.textContent = `p2–p98 contrast · Global range: ${formatLegendTick(rawMin, isRaw)}–${formatLegendTick(rawMax, isRaw)}`;
      boundsEl.classList.remove("hidden");
    } else if (scaleMode === "log") {
      boundsEl.textContent = `Logarithmic scale · Range: ${formatLegendTick(rawMin ?? minVal, isRaw)}–${formatLegendTick(rawMax ?? maxVal, isRaw)}`;
      boundsEl.classList.remove("hidden");
    } else {
      boundsEl.classList.add("hidden");
    }
  }
}

export function buildFillColorExpression({
  valExpr,
  effectiveCutoff,
  paletteStops,
  minVal,
  maxVal,
  scaleMode = "auto",
  dimWellKnown = false,
}) {
  const span = Math.max(1e-6, maxVal - minVal);
  const mappedStops = [];
  for (const [t, col] of paletteStops) {
    const x =
      scaleMode === "log"
        ? (Math.pow(1 + LOG_SCALE_K, t) - 1) / LOG_SCALE_K
        : t;
    const v = minVal + x * span;
    if (!mappedStops.length || v > mappedStops[mappedStops.length - 2] + 1e-6) {
      mappedStops.push(v, col);
    }
  }

  const rampExpr = ["interpolate", ["linear"], valExpr, ...mappedStops];
  if (dimWellKnown) {
    return [
      "case",
      ["boolean", ["get", "is_well_known"], false],
      "#1e293b",
      ["<", valExpr, effectiveCutoff],
      "rgba(15, 23, 42, 0.0)",
      rampExpr,
    ];
  }

  return [
    "case",
    ["<", valExpr, effectiveCutoff],
    "rgba(15, 23, 42, 0.0)",
    rampExpr,
  ];
}

export function buildFillOpacityExpression({
  valExpr,
  isScoreLayer,
  effectiveCutoff,
  hexOpacity,
  minVal,
  maxVal,
  dimWellKnown = false,
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

  const rampOpacity = [
    "interpolate",
    ["linear"],
    valExpr,
    sLow,
    Number((hexOpacity * 0.46).toFixed(3)),
    sMid,
    Number((hexOpacity * 0.76).toFixed(3)),
    sHigh,
    Number((hexOpacity * 0.94).toFixed(3)),
    maxVal,
    Number(hexOpacity.toFixed(3)),
  ];

  if (dimWellKnown) {
    return [
      "case",
      ["boolean", ["get", "is_well_known"], false],
      0.34,
      ["<", valExpr, effectiveCutoff],
      0.0,
      rampOpacity,
    ];
  }

  return [
    "case",
    ["<", valExpr, effectiveCutoff],
    0.0,
    rampOpacity,
  ];
}

export function buildOutlineOpacityExpression({ isScoreLayer = true }) {
  const midOp = isScoreLayer ? 0.18 : 0.16;
  const highOp = isScoreLayer ? 0.45 : 0.42;
  // Keep ["zoom"] top-level without data/feature-state sub-expressions in zoom stops
  return [
    "interpolate",
    ["linear"],
    ["zoom"],
    2.2,
    0.0,
    3.3,
    midOp,
    5.2,
    highOp,
  ];
}

export function buildOutlineColorExpression({ valExpr, isScoreLayer = true, effectiveCutoff }) {
  const hiddenCond = isScoreLayer ? ["<", valExpr, effectiveCutoff] : ["<=", valExpr, -99999];
  return ["case", hiddenCond, "rgba(0, 0, 0, 0)", "rgba(226, 232, 240, 0.55)"];
}
