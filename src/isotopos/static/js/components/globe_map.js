// 3D Earth Globe (MapLibre GL JS), starfield backdrop, layer coloring & legend

import { fetchRawParameter } from "../api.js";
import { PALETTES, state } from "../state.js";

export function initStarfield() {
  const canvas = document.getElementById("starfield-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  function renderStars() {
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = Math.max(300, Math.floor(rect.width));
    canvas.height = Math.max(300, Math.floor(rect.height));
    const w = canvas.width;
    const h = canvas.height;

    ctx.clearRect(0, 0, w, h);

    const grad = ctx.createRadialGradient(w * 0.5, h * 0.5, w * 0.12, w * 0.5, h * 0.5, w * 0.65);
    grad.addColorStop(0, "rgba(14, 116, 144, 0.16)");
    grad.addColorStop(0.5, "rgba(30, 58, 138, 0.08)");
    grad.addColorStop(1, "rgba(2, 6, 23, 0.0)");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, w, h);

    let seed = 1337;
    const rand = () => {
      seed = (seed * 16807) % 2147483647;
      return (seed - 1) / 2147483646;
    };

    const starCount = 320;
    for (let i = 0; i < starCount; i++) {
      const x = rand() * w;
      const y = rand() * h;
      const r = rand() < 0.85 ? 0.6 + rand() * 0.7 : 1.3 + rand() * 1.1;
      const alpha = 0.25 + rand() * 0.7;
      const tint = rand() < 0.3 ? "186, 230, 253" : rand() < 0.6 ? "254, 243, 199" : "241, 245, 249";
      ctx.fillStyle = `rgba(${tint}, ${alpha.toFixed(2)})`;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  renderStars();
  window.addEventListener("resize", renderStars);
}

export function updateLegendGradient() {
  const bar = document.getElementById("legend-gradient-bar");
  if (!bar) return;
  const stops = PALETTES[state.palette] || PALETTES.bioluminescent;
  const cssStops = stops.map(([t, col]) => `${col} ${Math.round(t * 100)}%`).join(", ");
  bar.style.background = `linear-gradient(90deg, ${cssStops})`;
}

export function populateLayerSwitcher() {
  const sel = document.getElementById("layer-variable-select");
  if (!sel) return;
  sel.innerHTML = "";

  const overallOpt = document.createElement("option");
  overallOpt.value = "overall_score";
  overallOpt.textContent = "Overall Similarity Score (%)";
  sel.appendChild(overallOpt);

  const dimGroup = document.createElement("optgroup");
  dimGroup.label = "Dimension Sub-Scores";
  for (const dim of state.metadata.dimensions) {
    const opt = document.createElement("option");
    opt.value = `dim:${dim.id}`;
    opt.textContent = `Dim: ${dim.name}`;
    dimGroup.appendChild(opt);
  }
  sel.appendChild(dimGroup);

  const rawGroup = document.createElement("optgroup");
  rawGroup.label = "Raw Earth Physical Parameters";
  for (const p of state.metadata.parameters) {
    const opt = document.createElement("option");
    opt.value = `raw:${p.id}`;
    opt.textContent = `Raw: ${p.label} (${p.unit})`;
    rawGroup.appendChild(opt);
  }
  sel.appendChild(rawGroup);
}

export function initEarthMap({ onInspectSite }) {
  const style = {
    version: 8,
    projection: { type: "globe" },
    sky: {
      "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 0.88, 5, 0.38, 7, 0.0],
    },
    sources: {
      gibs_bluemarble: {
        type: "raster",
        tiles: [
          "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_NextGeneration/default/2004-08-01/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg",
        ],
        tileSize: 256,
        maxzoom: 8,
        attribution: "NASA GIBS / Earthdata",
      },
      gibs_modis: {
        type: "raster",
        tiles: [
          "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/2024-07-15/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg",
        ],
        tileSize: 256,
        maxzoom: 9,
        attribution: "NASA Worldview GIBS",
      },
    },
    layers: [
      { id: "bg", type: "background", paint: { "background-color": "rgba(4, 8, 18, 0.0)" } },
      { id: "gibs_bluemarble", type: "raster", source: "gibs_bluemarble" },
      {
        id: "gibs_modis",
        type: "raster",
        source: "gibs_modis",
        layout: { visibility: "none" },
      },
    ],
  };

  const map = new maplibregl.Map({
    container: "earth-map",
    style,
    center: [-20, 28],
    zoom: 1.55,
  });

  map.addControl(new maplibregl.NavigationControl(), "top-right");

  const pauseSpin = () => {
    state.userInteracting = true;
  };
  const resumeSpin = () => {
    state.userInteracting = false;
  };
  map.on("mousedown", pauseSpin);
  map.on("touchstart", pauseSpin);
  map.on("wheel", () => {
    state.userInteracting = true;
    clearTimeout(map._wheelTimeout);
    map._wheelTimeout = setTimeout(resumeSpin, 2200);
  });
  map.on("mouseup", resumeSpin);
  map.on("touchend", resumeSpin);

  map.on("style.load", () => {
    map.setProjection({ type: state.isGlobe ? "globe" : "mercator" });
  });

  map.on("load", () => {
    map.addSource("earth-h3", {
      type: "geojson",
      data: state.earthGeojson,
      promoteId: "id",
    });

    map.addLayer({
      id: "earth-h3-fill",
      type: "fill",
      source: "earth-h3",
      paint: {
        "fill-color": "#06b6d4",
        "fill-opacity": 0.0,
        "fill-antialias": false,
      },
    });

    map.addLayer({
      id: "earth-h3-outline",
      type: "line",
      source: "earth-h3",
      paint: {
        "line-color": "rgba(226, 232, 240, 0.55)",
        "line-width": ["interpolate", ["linear"], ["zoom"], 2.0, 0.2, 4.0, 0.6, 6.5, 1.2],
        "line-opacity": ["interpolate", ["linear"], ["zoom"], 2.2, 0.0, 3.3, 0.18, 5.2, 0.45],
      },
    });

    map.addLayer({
      id: "earth-h3-selected",
      type: "line",
      source: "earth-h3",
      filter: ["==", ["get", "id"], ""],
      paint: {
        "line-color": "#38bdf8",
        "line-width": 2.6,
        "line-opacity": 0.98,
      },
    });

    map.addSource("earth-hotspots", {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });

    map.addLayer({
      id: "earth-hotspots-glow",
      type: "circle",
      source: "earth-hotspots",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 1.5, 10, 5.0, 15],
        "circle-color": ["case", ["get", "is_well_known"], "#f59e0b", "#38bdf8"],
        "circle-opacity": 0.28,
        "circle-blur": 0.65,
      },
    });

    map.addLayer({
      id: "earth-hotspots-circle",
      type: "circle",
      source: "earth-hotspots",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 1.5, 5.5, 5.0, 8.0],
        "circle-color": ["case", ["get", "is_well_known"], "#f59e0b", "#38bdf8"],
        "circle-stroke-width": 1.6,
        "circle-stroke-color": "#ffffff",
      },
    });

    const tooltip = document.getElementById("hover-tooltip");

    map.on("mousemove", (e) => {
      const hits = map.queryRenderedFeatures(e.point, {
        layers: ["earth-hotspots-circle", "earth-h3-fill"],
      });
      if (!hits.length) {
        map.getCanvas().style.cursor = "";
        tooltip.classList.add("hidden");
        return;
      }

      const top = hits[0];
      if (top.layer.id === "earth-hotspots-circle") {
        const p = top.properties;
        const kind = p.is_well_known ? "Baseline Hotspot" : "Novel Hotspot";
        map.getCanvas().style.cursor = "pointer";
        tooltip.innerHTML = `<strong>${p.name}</strong><br/>${kind}<br/>Similarity: <b>${p.score_pct}%</b>`;
        tooltip.style.left = `${e.point.x + 14}px`;
        tooltip.style.top = `${e.point.y + 14}px`;
        tooltip.classList.remove("hidden");
        return;
      }

      const props = top.properties;
      const val = state.cellDisplayValues[props.id] ?? top.state?.display_val ?? -999999;
      const isRaw = state.activeLayer.startsWith("raw:");
      const cutoff = isRaw ? -99999 : state.minScoreFilter;
      if (val <= -99999 || val < cutoff) {
        map.getCanvas().style.cursor = "";
        tooltip.classList.add("hidden");
        return;
      }

      map.getCanvas().style.cursor = "pointer";
      let unitLabel = "%";
      if (isRaw) {
        const param = state.metadata.parameters.find((pm) => pm.id === state.activeLayer.slice(4));
        unitLabel = param ? ` ${param.unit}` : "";
      }
      tooltip.innerHTML = `<strong>${props.name}</strong><br/>${props.region}<br/>Value: <b>${Number(val).toFixed(1)}${unitLabel}</b>`;
      tooltip.style.left = `${e.point.x + 14}px`;
      tooltip.style.top = `${e.point.y + 14}px`;
      tooltip.classList.remove("hidden");
    });

    map.on("mouseleave", "earth-h3-fill", () => {
      map.getCanvas().style.cursor = "";
      tooltip.classList.add("hidden");
    });

    map.on("click", (e) => {
      const hits = map.queryRenderedFeatures(e.point, {
        layers: ["earth-hotspots-circle", "earth-h3-fill"],
      });
      if (!hits.length) return;
      const top = hits[0];
      if (top.layer.id === "earth-hotspots-circle") {
        onInspectSite(top.properties.id);
        return;
      }
      const id = top.properties.id;
      const val = state.cellDisplayValues[id] ?? -999999;
      if (val > -99999) {
        onInspectSite(id);
      }
    });

    state.mapReady = true;
    updateEarthMapLayers(true);
  });

  state.map = map;
}

export function resizeEarthMap() {
  state.map?.resize();
}

export function applyBasemap(basemapId) {
  state.basemap = basemapId;
  if (!state.map) return;
  const useDark = basemapId === "dark_vector";
  const useModis = basemapId === "gibs_modis";
  state.map.setLayoutProperty("gibs_bluemarble", "visibility", useModis ? "none" : "visible");
  state.map.setPaintProperty("gibs_bluemarble", "raster-brightness-max", useDark ? 0.22 : 1.0);
  state.map.setPaintProperty("gibs_bluemarble", "raster-saturation", useDark ? -0.95 : 0.0);
  state.map.setPaintProperty("gibs_bluemarble", "raster-opacity", useDark ? 0.88 : 1.0);
  state.map.setLayoutProperty("gibs_modis", "visibility", useModis ? "visible" : "none");
}

export function startAutoSpinLoop() {
  let lastTime = performance.now();
  function frame(now) {
    const dt = (now - lastTime) / 1000.0;
    lastTime = now;
    if (
      state.map &&
      state.isGlobe &&
      state.autoSpin &&
      !state.userInteracting &&
      state.map.getZoom() < 2.8
    ) {
      const center = state.map.getCenter();
      center.lng = ((center.lng + dt * 2.4 + 180) % 360) - 180;
      state.map.setCenter(center);
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}

function formatTick(val, isRaw) {
  if (isRaw) {
    return Math.abs(val) >= 100 ? String(Math.round(val)) : val.toFixed(1);
  }
  return `${Math.round(val)}%`;
}

async function ensureRawParameterLoaded(paramId) {
  if (state.rawParamCache[paramId]) return state.rawParamCache[paramId];
  state.rawParamCache[paramId] = await fetchRawParameter(paramId);
  return state.rawParamCache[paramId];
}

export async function updateEarthMapLayers(updateData = true) {
  if (!state.map || !state.mapReady || !state.map.getLayer("earth-h3-fill") || !state.lastRankResponse) {
    return;
  }

  const seq = ++state.renderSeq;
  const { cell_scores, cell_dimension_scores, hotspot_results } = state.lastRankResponse;
  const layerKey = state.activeLayer;

  let legendTitle = "Overall Similarity (%)";
  let isScoreLayer = true;
  let paramSpec = null;

  if (layerKey.startsWith("dim:")) {
    const dimId = layerKey.slice(4);
    const dim = state.metadata.dimensions.find((d) => d.id === dimId);
    legendTitle = `${dim?.name || dimId} Match (%)`;
  } else if (layerKey.startsWith("raw:")) {
    isScoreLayer = false;
    const pId = layerKey.slice(4);
    paramSpec = state.metadata.parameters.find((p) => p.id === pId);
    legendTitle = `${paramSpec.label} (${paramSpec.unit})`;
  }

  const minScoreRow = document.getElementById("min-score-filter")?.closest(".overlay-row");
  if (minScoreRow) {
    minScoreRow.classList.toggle("disabled", !isScoreLayer);
  }

  if (updateData) {
    let rawMap = null;
    if (layerKey.startsWith("raw:")) {
      rawMap = await ensureRawParameterLoaded(layerKey.slice(4));
      if (seq !== state.renderSeq) return;
    }

    const dimId = layerKey.startsWith("dim:") ? layerKey.slice(4) : null;
    for (const feat of state.earthGeojson.features) {
      const id = feat.properties.id;
      let val = -999999;
      if (id in cell_scores) {
        if (layerKey === "overall_score") {
          val = cell_scores[id] * 100.0;
        } else if (dimId) {
          const sub = cell_dimension_scores[id]?.[dimId];
          val = sub === null || sub === undefined ? -999999 : sub * 100.0;
        } else if (rawMap) {
          val = rawMap[id] ?? -999999;
        }
      }
      state.cellDisplayValues[id] = val;
      state.map.setFeatureState({ source: "earth-h3", id }, { display_val: val });
    }
  }

  const effectiveCutoff = isScoreLayer ? state.minScoreFilter : -99999;

  let dataMin = Infinity;
  let dataMax = -Infinity;
  let validCount = 0;
  for (const feat of state.earthGeojson.features) {
    const v = state.cellDisplayValues[feat.properties.id] ?? -999999;
    if (v <= -99999) continue;
    if (isScoreLayer && v < effectiveCutoff) continue;
    validCount += 1;
    if (v < dataMin) dataMin = v;
    if (v > dataMax) dataMax = v;
  }

  let minVal = 0;
  let maxVal = 100;
  if (!isScoreLayer && paramSpec) {
    if (state.scaleMode === "auto" && validCount > 0) {
      minVal = dataMin;
      maxVal = dataMax;
    } else {
      minVal = paramSpec.earth_min;
      maxVal = paramSpec.earth_max;
    }
  } else if (state.scaleMode === "auto" && validCount > 0) {
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

  if (layerKey.startsWith("dim:") && validCount === 0 && Object.keys(cell_scores).length > 0) {
    legendTitle = `${legendTitle} — N/A (0% weights)`;
  }

  const minLabel = formatTick(minVal, !isScoreLayer);
  const maxLabel = formatTick(maxVal, !isScoreLayer);
  document.getElementById("legend-title").textContent = legendTitle;
  document.getElementById("legend-min").textContent = minLabel;
  document.getElementById("legend-mid").textContent = formatTick((minVal + maxVal) / 2, !isScoreLayer);
  document.getElementById("legend-max").textContent = maxLabel;
  const legendSummary = document.getElementById("summary-legend");
  if (legendSummary) legendSummary.textContent = `${minLabel}–${maxLabel}`;

  const paletteStops = PALETTES[state.palette] || PALETTES.bioluminescent;
  const valExpr = ["coalesce", ["feature-state", "display_val"], -999999];

  const colorExpr = [
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

  const span = Math.max(1e-6, maxVal - minVal);
  const sLow = minVal;
  const sMid = minVal + 0.45 * span;
  const sHigh = minVal + 0.78 * span;

  const opacityExpr = isScoreLayer
    ? [
        "case",
        ["<", valExpr, effectiveCutoff],
        0.0,
        [
          "interpolate",
          ["linear"],
          valExpr,
          sLow,
          Number((state.hexOpacity * 0.44).toFixed(3)),
          sMid,
          Number((state.hexOpacity * 0.74).toFixed(3)),
          sHigh,
          Number((state.hexOpacity * 0.95).toFixed(3)),
          maxVal,
          Number(state.hexOpacity.toFixed(3)),
        ],
      ]
    : [
        "case",
        ["<=", valExpr, -99999],
        0.0,
        Number((state.hexOpacity * 0.88).toFixed(3)),
      ];

  const outlineOpacityExpr = [
    "case",
    ["<", valExpr, effectiveCutoff],
    0.0,
    ["interpolate", ["linear"], ["zoom"], 2.2, 0.0, 3.3, 0.18, 5.2, 0.45],
  ];

  state.map.setPaintProperty("earth-h3-fill", "fill-color", colorExpr);
  state.map.setPaintProperty("earth-h3-fill", "fill-opacity", opacityExpr);
  state.map.setPaintProperty("earth-h3-outline", "line-opacity", outlineOpacityExpr);

  const hsFeatures = state.showHotspots
    ? hotspot_results.map((r) => ({
        type: "Feature",
        properties: {
          id: r.site.id,
          name: r.site.name,
          is_well_known: r.site.is_well_known,
          score_pct: Math.round(r.overall_score * 100),
        },
        geometry: {
          type: "Point",
          coordinates: [r.site.lon, r.site.lat],
        },
      }))
    : [];

  state.map.getSource("earth-hotspots")?.setData({
    type: "FeatureCollection",
    features: hsFeatures,
  });
}
