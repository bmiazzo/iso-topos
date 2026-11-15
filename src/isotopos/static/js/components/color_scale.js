// Scientific color palette scaling, legend formatting, and RGBA LUT helpers

import { PALETTES, state } from "../state.js";

const LOG_SCALE_K = 50.0;
const INV_LOG_1_PLUS_K = 1.0 / Math.log(1.0 + LOG_SCALE_K);
const _paletteLutCache = new Map();

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

let _cachedRangeKey = null;
let _cachedRangeResult = null;

export function computeLayerColorRange({
  features,
  cellDisplayValues,
  isScoreLayer,
  effectiveCutoff,
  scaleMode,
  paramSpec,
  dataVersion,
}) {
  const cacheKey =
    dataVersion !== undefined
      ? `${dataVersion}|${isScoreLayer}|${effectiveCutoff}|${scaleMode}|${paramSpec?.id || ""}`
      : null;
  if (cacheKey !== null && cacheKey === _cachedRangeKey && _cachedRangeResult) {
    return _cachedRangeResult;
  }

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

  const result = {
    minVal,
    midVal,
    maxVal,
    rawMin: validCount > 0 ? dataMin : minVal,
    rawMax: validCount > 0 ? dataMax : maxVal,
    isClipped,
    validCount,
  };
  if (cacheKey !== null) {
    _cachedRangeKey = cacheKey;
    _cachedRangeResult = result;
  }
  return result;
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

export function getPaletteLut(paletteName) {
  let lut = _paletteLutCache.get(paletteName);
  if (!lut) {
    const stops = PALETTES[paletteName] || PALETTES.bioluminescent;
    lut = new Uint8Array(256 * 3);
    for (let i = 0; i < 256; i++) {
      const [r, g, b] = samplePaletteRgb(stops, i / 255);
      const base = i * 3;
      lut[base] = r;
      lut[base + 1] = g;
      lut[base + 2] = b;
    }
    _paletteLutCache.set(paletteName, lut);
  }
  return lut;
}

export function writeCellRgbaBytes(
  outRgba,
  {
    val,
    isWellKnown = false,
    isScoreLayer = true,
    effectiveCutoff = 0,
    hexOpacity = 0.82,
    minVal = 0,
    maxVal = 100,
    invSpan = 0.01,
    lut,
    isLogScale = false,
    dimWellKnown = false,
  },
) {
  if (isScoreLayer) {
    if (dimWellKnown && isWellKnown) {
      outRgba[0] = 30;
      outRgba[1] = 41;
      outRgba[2] = 59;
      outRgba[3] = 87;
      return;
    }
    if (val <= -99999 || val < effectiveCutoff) {
      outRgba[0] = 15;
      outRgba[1] = 23;
      outRgba[2] = 42;
      outRgba[3] = 0;
      return;
    }
  } else if (val <= -99999) {
    outRgba[0] = 15;
    outRgba[1] = 23;
    outRgba[2] = 42;
    outRgba[3] = 0;
    return;
  }

  const rawU = (val - minVal) * invSpan;
  const u = rawU <= 0 ? 0 : rawU >= 1 ? 1 : rawU;
  const t = isLogScale ? Math.log(1.0 + LOG_SCALE_K * u) * INV_LOG_1_PLUS_K : u;
  const lutBase = ((t * 255 + 0.5) | 0) * 3;

  outRgba[0] = lut[lutBase];
  outRgba[1] = lut[lutBase + 1];
  outRgba[2] = lut[lutBase + 2];

  if (!isScoreLayer) {
    outRgba[3] = Math.round(hexOpacity * 0.88 * 255);
    return;
  }

  let opFactor;
  if (u <= 0.45) {
    opFactor = 0.46 + ((0.76 - 0.46) * u) / 0.45;
  } else if (u <= 0.78) {
    opFactor = 0.76 + ((0.94 - 0.76) * (u - 0.45)) / 0.33;
  } else {
    opFactor = 0.94 + ((1.0 - 0.94) * (u - 0.78)) / 0.22;
  }
  outRgba[3] = Math.round(hexOpacity * opFactor * 255);
}
