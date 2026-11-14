// iso-topos Dual-Mode 3D Globe Scientist UI (H3 Res 4 + Captivating Visualization)

const PALETTES = {
  bioluminescent: [
    [0.0, "#0b1938"],
    [0.3, "#0e4d7a"],
    [0.58, "#06b6d4"],
    [0.82, "#10b981"],
    [1.0, "#fef08a"],
  ],
  viridis: [
    [0.0, "#440154"],
    [0.25, "#3b528b"],
    [0.5, "#21918c"],
    [0.75, "#5ec962"],
    [1.0, "#fde725"],
  ],
  magma: [
    [0.0, "#140b34"],
    [0.3, "#51127c"],
    [0.6, "#b73779"],
    [0.82, "#fc8961"],
    [1.0, "#fcfdbf"],
  ],
  plasma: [
    [0.0, "#0d0887"],
    [0.3, "#6a00a8"],
    [0.6, "#b12a90"],
    [0.82, "#e16462"],
    [1.0, "#f0f921"],
  ],
  turbo: [
    [0.0, "#30123b"],
    [0.25, "#28bbec"],
    [0.5, "#a2fc3c"],
    [0.75, "#fb8022"],
    [1.0, "#7a0403"],
  ],
};

const state = {
  metadata: null,
  earthGeojson: null,
  rawParamCache: {},
  body: "moon",
  mode: "simple",
  scoringMode: "clamped",
  excludeWellKnown: false,
  showHotspots: true,
  isGlobe: true,
  autoSpin: true,
  userInteracting: false,
  activeTab: "hotspots",
  activeLayer: "overall_score",
  palette: "bioluminescent",
  basemap: "gibs_bluemarble",
  hexOpacity: 0.82,
  minScoreFilter: 0,
  target: null,
  weights: {},
  lastRankResponse: null,
  selectedSiteId: null,
  map: null,
  chart: null,
  rankDebounce: null,
};

async function init() {
  initStarfield();

  const [metaResp, geoResp] = await Promise.all([
    fetch("/api/v1/metadata"),
    fetch("/api/v1/earth-grid"),
  ]);
  state.metadata = await metaResp.json();
  state.earthGeojson = await geoResp.json();

  populateLayerSwitcher();
  populatePresetDropdown();
  buildAdvancedControls();
  updateLegendGradient();
  initEarthMap();
  bindUIEvents();
  startAutoSpinLoop();

  const firstPreset = state.metadata.presets.find((p) => p.body === state.body);
  if (firstPreset) {
    await selectPreset(firstPreset.id);
  }
}

function initStarfield() {
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

    // Subtle deep-space nebula glow
    const grad = ctx.createRadialGradient(w * 0.5, h * 0.5, w * 0.12, w * 0.5, h * 0.5, w * 0.65);
    grad.addColorStop(0, "rgba(14, 116, 144, 0.16)");
    grad.addColorStop(0.5, "rgba(30, 58, 138, 0.08)");
    grad.addColorStop(1, "rgba(2, 6, 23, 0.0)");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, w, h);

    // Deterministic star distribution
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

function updateLegendGradient() {
  const bar = document.getElementById("legend-gradient-bar");
  if (!bar) return;
  const stops = PALETTES[state.palette] || PALETTES.bioluminescent;
  const cssStops = stops.map(([t, col]) => `${col} ${Math.round(t * 100)}%`).join(", ");
  bar.style.background = `linear-gradient(90deg, ${cssStops})`;
}

function populateLayerSwitcher() {
  const sel = document.getElementById("layer-variable-select");
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

function populatePresetDropdown() {
  const sel = document.getElementById("preset-select");
  sel.innerHTML = "";
  const bodyPresets = state.metadata.presets.filter((p) => p.body === state.body);
  for (const p of bodyPresets) {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = `${p.name} (${p.lat.toFixed(1)}°, ${p.lon.toFixed(1)}°E)`;
    sel.appendChild(opt);
  }
}

function buildAdvancedControls() {
  const container = document.getElementById("parameter-weights-container");
  container.innerHTML = "";

  for (const dim of state.metadata.dimensions) {
    const group = document.createElement("div");
    group.className = "dim-group";
    group.innerHTML = `<h3>${dim.name}</h3>`;

    const dimParams = state.metadata.parameters.filter((p) => p.dimension_id === dim.id);
    for (const p of dimParams) {
      const row = document.createElement("div");
      row.className = "param-row";
      row.innerHTML = `
        <div class="param-row-top">
          <span title="${p.description}">${p.label} <small>(${p.unit})</small></span>
          <label><input type="checkbox" id="chk-en-${p.id}" checked /> Active</label>
        </div>
        <div class="param-row-controls">
          <input type="number" class="param-override-input" id="val-${p.id}" step="any" title="Override target value" />
          <input type="range" id="wt-${p.id}" min="0" max="100" step="5" value="80" />
          <span id="wt-lbl-${p.id}">80%</span>
        </div>
      `;
      group.appendChild(row);

      const valInput = row.querySelector(`#val-${p.id}`);
      const wtSlider = row.querySelector(`#wt-${p.id}`);
      const wtLabel = row.querySelector(`#wt-lbl-${p.id}`);
      const chkEnable = row.querySelector(`#chk-en-${p.id}`);

      valInput.addEventListener("change", () => {
        if (!state.target) return;
        state.target.parameters[p.id] = parseFloat(valInput.value) || 0;
        scheduleRank();
      });

      wtSlider.addEventListener("input", () => {
        const w = parseInt(wtSlider.value, 10) / 100.0;
        state.weights[p.id] = w;
        wtLabel.textContent = `${wtSlider.value}%`;
        chkEnable.checked = w > 0;
        scheduleRank();
      });

      chkEnable.addEventListener("change", () => {
        if (!chkEnable.checked) {
          state.weights[p.id] = 0.0;
          wtSlider.value = "0";
          wtLabel.textContent = "0%";
        } else {
          const restored = p.default_weight > 0 ? Math.round(p.default_weight * 100) : 50;
          state.weights[p.id] = restored / 100.0;
          wtSlider.value = String(restored);
          wtLabel.textContent = `${restored}%`;
        }
        scheduleRank();
      });
    }
    container.appendChild(group);
  }
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
}

async function selectPreset(presetId) {
  const resp = await fetch("/api/v1/target/extract", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ preset_id: presetId }),
  });
  const target = await resp.json();
  state.target = target;
  state.weights = { ...(target.recommended_weights || {}) };
  document.getElementById("preset-select").value = presetId;
  document.getElementById("preset-context").textContent =
    `${target.mission_context || ""} — ${target.notes || ""}`;
  syncControlsFromTarget();
  await runRank();
}

async function extractCoordinate(lat, lon) {
  const resp = await fetch("/api/v1/target/extract", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ body: state.body, lat, lon }),
  });
  const target = await resp.json();
  state.target = target;
  document.getElementById("preset-context").textContent = target.notes || "";
  syncControlsFromTarget();
  await runRank();
}

function buildActiveFilters() {
  const filters = [];
  const maxSlope = parseFloat(document.getElementById("flt-max-slope").value);
  if (!Number.isNaN(maxSlope)) filters.push({ parameter_id: "slope_deg", max_value: maxSlope });

  const minTemp = parseFloat(document.getElementById("flt-min-temp").value);
  const maxTemp = parseFloat(document.getElementById("flt-max-temp").value);
  if (!Number.isNaN(minTemp) || !Number.isNaN(maxTemp)) {
    filters.push({
      parameter_id: "mean_temp_c",
      min_value: Number.isNaN(minTemp) ? null : minTemp,
      max_value: Number.isNaN(maxTemp) ? null : maxTemp,
    });
  }

  const minAridity = parseFloat(document.getElementById("flt-min-aridity").value);
  if (!Number.isNaN(minAridity)) {
    filters.push({ parameter_id: "aridity_dryness_index", min_value: minAridity });
  }
  return filters;
}

function scheduleRank() {
  clearTimeout(state.rankDebounce);
  state.rankDebounce = setTimeout(runRank, 110);
}

async function ensureRawParameterLoaded(paramId) {
  if (state.rawParamCache[paramId]) return state.rawParamCache[paramId];
  const resp = await fetch(`/api/v1/earth-grid/parameter/${paramId}`);
  const data = await resp.json();
  state.rawParamCache[paramId] = data.values || {};
  return state.rawParamCache[paramId];
}

async function runRank() {
  if (!state.target) return;
  const t0 = performance.now();
  const activeDimId = state.activeLayer.startsWith("dim:") ? state.activeLayer.slice(4) : null;

  const payload = {
    target: state.target,
    weights: state.weights,
    mode: state.scoringMode,
    filters: buildActiveFilters(),
    exclude_well_known: state.excludeWellKnown,
    top_k: 15,
    dimension_id: activeDimId,
  };

  const resp = await fetch("/api/v1/rank", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await resp.json();
  state.lastRankResponse = data;

  const dt = Math.round(performance.now() - t0);
  document.getElementById("eval-timing").textContent = `${data.filtered_h3_count.toLocaleString()} cells • ${dt} ms`;
  document.getElementById("all-zero-warning").classList.toggle("hidden", !data.all_weights_zero);

  await updateEarthMapLayers(true);
  renderRankedList();

  const defaultPool = state.activeTab === "hotspots" ? data.hotspot_results : data.top_h3_results;
  if (defaultPool.length > 0) {
    const existing = [...data.hotspot_results, ...data.top_h3_results].find(
      (r) => r.site.id === state.selectedSiteId
    );
    showBreakdown(existing || defaultPool[0]);
  }
}

async function inspectAnySiteById(siteId) {
  if (!state.target || !siteId) return;
  const cached = [
    ...(state.lastRankResponse?.hotspot_results || []),
    ...(state.lastRankResponse?.top_h3_results || []),
  ].find((r) => r.site.id === siteId);
  if (cached) {
    showBreakdown(cached);
    return;
  }

  const resp = await fetch(`/api/v1/site/${encodeURIComponent(siteId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      target: state.target,
      weights: state.weights,
      mode: state.scoringMode,
    }),
  });
  if (resp.ok) {
    const result = await resp.json();
    showBreakdown(result);
  }
}

function initEarthMap() {
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
    });

    map.addLayer({
      id: "earth-h3-fill",
      type: "fill",
      source: "earth-h3",
      paint: {
        "fill-color": "#06b6d4",
        "fill-opacity": state.hexOpacity,
        "fill-antialias": false,
      },
    });

    // Zoom-adaptive honeycomb outlines: invisible from space, crisp hexagonal mesh when zoomed in
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

    // Selected H3 hexagon highlight ring
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

    // Outer glow halo on hotspots
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

    map.on("mousemove", "earth-h3-fill", (e) => {
      if (!e.features?.length) return;
      const props = e.features[0].properties;
      const val = props._display_val ?? -999999;
      if (val <= -99999) {
        map.getCanvas().style.cursor = "";
        tooltip.classList.add("hidden");
        return;
      }
      map.getCanvas().style.cursor = "pointer";
      const unitSuffix = state.activeLayer.startsWith("raw:") ? "" : "%";
      tooltip.innerHTML = `<strong>${props.name}</strong><br/>${props.region}<br/>Value: <b>${Number(val).toFixed(1)}${unitSuffix}</b>`;
      tooltip.style.left = `${e.point.x + 14}px`;
      tooltip.style.top = `${e.point.y + 14}px`;
      tooltip.classList.remove("hidden");
    });

    map.on("mouseleave", "earth-h3-fill", () => {
      map.getCanvas().style.cursor = "";
      tooltip.classList.add("hidden");
    });

    map.on("click", "earth-hotspots-circle", (e) => {
      if (!e.features?.length) return;
      const id = e.features[0].properties.id;
      inspectAnySiteById(id);
    });

    map.on("click", "earth-h3-fill", (e) => {
      if (!e.features?.length) return;
      const id = e.features[0].properties.id;
      inspectAnySiteById(id);
    });

    updateEarthMapLayers(true);
  });

  state.map = map;
}

function startAutoSpinLoop() {
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

async function updateEarthMapLayers(updateData = true) {
  if (!state.map || !state.map.isStyleLoaded() || !state.lastRankResponse) return;

  const { cell_scores, cell_dimension_scores, hotspot_results } = state.lastRankResponse;
  const layerKey = state.activeLayer;

  let minVal = 0;
  let maxVal = 100;
  let legendTitle = "Overall Similarity (%)";
  let isScoreLayer = true;

  if (layerKey.startsWith("dim:")) {
    const dimId = layerKey.slice(4);
    const dim = state.metadata.dimensions.find((d) => d.id === dimId);
    legendTitle = `${dim?.name || dimId} Match (%)`;
  } else if (layerKey.startsWith("raw:")) {
    isScoreLayer = false;
    const pId = layerKey.slice(4);
    const param = state.metadata.parameters.find((p) => p.id === pId);
    minVal = param.earth_min;
    maxVal = param.earth_max;
    legendTitle = `${param.label} (${param.unit})`;
  }

  document.getElementById("legend-title").textContent = legendTitle;
  document.getElementById("legend-min").textContent = `${minVal}`;
  document.getElementById("legend-mid").textContent = `${Math.round((minVal + maxVal) / 2)}`;
  document.getElementById("legend-max").textContent = `${maxVal}`;

  if (updateData) {
    let rawMap = null;
    if (layerKey.startsWith("raw:")) {
      rawMap = await ensureRawParameterLoaded(layerKey.slice(4));
    }

    const dimId = layerKey.startsWith("dim:") ? layerKey.slice(4) : null;
    for (const feat of state.earthGeojson.features) {
      const id = feat.properties.id;
      if (!(id in cell_scores)) {
        feat.properties._display_val = -999999;
        continue;
      }

      if (layerKey === "overall_score") {
        feat.properties._display_val = cell_scores[id] * 100.0;
      } else if (dimId) {
        const sub = cell_dimension_scores[id]?.[dimId];
        feat.properties._display_val = sub === null || sub === undefined ? -999999 : sub * 100.0;
      } else if (rawMap) {
        feat.properties._display_val = rawMap[id] ?? 0;
      }
    }

    state.map.getSource("earth-h3")?.setData(state.earthGeojson);
  }

  const paletteStops = PALETTES[state.palette] || PALETTES.bioluminescent;
  const effectiveCutoff = isScoreLayer ? Math.max(minVal, state.minScoreFilter) : minVal;

  const colorExpr = [
    "case",
    ["<", ["get", "_display_val"], effectiveCutoff],
    "rgba(15, 23, 42, 0.0)",
    [
      "interpolate",
      ["linear"],
      ["get", "_display_val"],
      ...paletteStops.flatMap(([t, col]) => [minVal + t * (maxVal - minVal), col]),
    ],
  ];

  // Score-driven dynamic opacity: low-scoring cells are translucent, top matches glow vividly
  const span = Math.max(1e-6, maxVal - effectiveCutoff);
  const sLow = effectiveCutoff;
  const sMid = effectiveCutoff + 0.45 * span;
  const sHigh = effectiveCutoff + 0.78 * span;

  const opacityExpr = isScoreLayer
    ? [
        "case",
        ["<", ["get", "_display_val"], effectiveCutoff],
        0.0,
        [
          "interpolate",
          ["linear"],
          ["get", "_display_val"],
          sLow,
          Number((state.hexOpacity * 0.24).toFixed(3)),
          sMid,
          Number((state.hexOpacity * 0.58).toFixed(3)),
          sHigh,
          Number((state.hexOpacity * 0.92).toFixed(3)),
          maxVal,
          Number(state.hexOpacity.toFixed(3)),
        ],
      ]
    : [
        "case",
        ["<=", ["get", "_display_val"], -99999],
        0.0,
        Number((state.hexOpacity * 0.85).toFixed(3)),
      ];

  state.map.setPaintProperty("earth-h3-fill", "fill-color", colorExpr);
  state.map.setPaintProperty("earth-h3-fill", "fill-opacity", opacityExpr);
  state.map.setFilter("earth-h3-outline", [">=", ["get", "_display_val"], effectiveCutoff]);

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

function renderRankedList() {
  const listEl = document.getElementById("ranked-list");
  listEl.innerHTML = "";
  const results =
    state.activeTab === "hotspots"
      ? state.lastRankResponse.hotspot_results
      : state.lastRankResponse.top_h3_results;

  for (const r of results) {
    const item = document.createElement("div");
    item.className = `rank-item ${r.site.id === state.selectedSiteId ? "selected" : ""}`;
    const pct = (r.overall_score * 100).toFixed(1);
    const tag = r.site.site_type === "hotspot" ? (r.site.is_well_known ? "Baseline" : "Novel") : "H3 Res 4";
    item.innerHTML = `
      <div>
        <div class="rank-item-name">${r.site.name}</div>
        <div class="rank-item-sub">${r.site.region} • ${tag}</div>
      </div>
      <div class="score-pill">${pct}%</div>
    `;
    item.addEventListener("click", () => {
      state.userInteracting = true;
      showBreakdown(r);
      state.map?.flyTo({ center: [r.site.lon, r.site.lat], zoom: 4.5 });
      setTimeout(() => {
        state.userInteracting = false;
      }, 2500);
    });
    listEl.appendChild(item);
  }
}

function showBreakdown(result) {
  state.selectedSiteId = result.site.id;
  if (state.map && state.map.getLayer("earth-h3-selected")) {
    state.map.setFilter("earth-h3-selected", ["==", ["get", "id"], result.site.id]);
  }

  document.getElementById("breakdown-card").classList.remove("hidden");
  document.getElementById("detail-name").textContent = result.site.name;
  document.getElementById("detail-meta").textContent =
    `${result.site.region} (${result.site.lat.toFixed(2)}°, ${result.site.lon.toFixed(2)}°)`;
  document.getElementById("detail-score-badge").textContent = `${(result.overall_score * 100).toFixed(1)}%`;
  document.getElementById("detail-notes").textContent = result.site.notes || "";

  // Render Dimension Bar Chart
  const labels = result.dimension_breakdowns.map((d) =>
    d.sub_score === null ? `${d.dimension_name} (N/A)` : d.dimension_name
  );
  const values = result.dimension_breakdowns.map((d) =>
    d.sub_score === null ? 0 : Math.round(d.sub_score * 100)
  );
  const colors = result.dimension_breakdowns.map((d) =>
    d.status === "N/A"
      ? "#475569"
      : d.status === "strong"
      ? "#2dd4bf"
      : d.status === "moderate"
      ? "#38bdf8"
      : "#f59e0b"
  );

  if (state.chart) state.chart.destroy();
  const ctx = document.getElementById("dimension-chart").getContext("2d");
  state.chart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{ label: "Dimension Similarity (%)", data: values, backgroundColor: colors }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { min: 0, max: 100, ticks: { color: "#93a4c3" }, grid: { color: "#27324a" } },
        y: { ticks: { color: "#e6edf7", font: { size: 10 } }, grid: { display: false } },
      },
      plugins: { legend: { display: false } },
    },
  });

  // Relevance
  const relEl = document.getElementById("detail-relevance");
  relEl.innerHTML = "";
  for (const item of result.exploration_relevance) {
    const li = document.createElement("li");
    li.textContent = item;
    relEl.appendChild(li);
  }

  // Earth-Limit Caveats
  const cavEl = document.getElementById("detail-caveats");
  cavEl.innerHTML = "";
  for (const c of result.earth_limit_caveats) {
    const div = document.createElement("div");
    div.className = "caveat-card";
    div.innerHTML = `<strong>${c.title}</strong><span>${c.explanation}</span>`;
    cavEl.appendChild(div);
  }

  // Provenance & Unit-Level Comparison Table
  const tbody = document.getElementById("detail-comparison-body");
  tbody.innerHTML = "";
  for (const comp of result.parameter_comparisons) {
    const pSpec = state.metadata.parameters.find((p) => p.id === comp.parameter_id);
    const pProv = state.body === "moon" ? pSpec.moon_provenance : pSpec.mars_provenance;
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${comp.label}<br/><small>${comp.unit}</small></td>
      <td>${comp.earth_value}</td>
      <td>${comp.target_value}</td>
      <td>${comp.weight === 0 ? "N/A" : Math.round(comp.similarity * 100) + "%"}</td>
      <td>
        <a href="${pSpec.earth_provenance.url}" target="_blank" rel="noopener">${pSpec.earth_provenance.agency_mission}</a> /
        <a href="${pProv.url}" target="_blank" rel="noopener">${pProv.agency_mission}</a>
      </td>
    `;
    tbody.appendChild(tr);
  }

  renderRankedList();
}

function drawPlanetaryPicker() {
  const canvas = document.getElementById("planetary-picker-canvas");
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;

  ctx.fillStyle = state.body === "moon" ? "#1e2430" : "#3a1e16";
  ctx.fillRect(0, 0, w, h);

  ctx.fillStyle = state.body === "moon" ? "rgba(15, 18, 26, 0.45)" : "rgba(95, 42, 24, 0.35)";
  for (let i = 0; i < 18; i++) {
    const rx = ((i * 73) % 280) + 10;
    const ry = ((i * 41) % 120) + 15;
    ctx.beginPath();
    ctx.arc(rx, ry, 10 + (i % 14), 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  ctx.lineWidth = 1;
  for (let gx = 0; gx <= w; gx += w / 6) {
    ctx.beginPath();
    ctx.moveTo(gx, 0);
    ctx.lineTo(gx, h);
    ctx.stroke();
  }
  for (let gy = 0; gy <= h; gy += h / 4) {
    ctx.beginPath();
    ctx.moveTo(0, gy);
    ctx.lineTo(w, gy);
    ctx.stroke();
  }

  for (const p of state.metadata.presets.filter((pr) => pr.body === state.body)) {
    const lonNorm = ((p.lon % 360) + 360) % 360;
    const x = (lonNorm / 360) * w;
    const y = ((90 - p.lat) / 180) * h;
    ctx.fillStyle = "#93a4c3";
    ctx.beginPath();
    ctx.arc(x, y, 3, 0, Math.PI * 2);
    ctx.fill();
  }

  if (state.target) {
    const lonNorm = ((state.target.lon % 360) + 360) % 360;
    const x = (lonNorm / 360) * w;
    const y = ((90 - state.target.lat) / 180) * h;
    ctx.strokeStyle = "#38bdf8";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(x, y, 6, 0, Math.PI * 2);
    ctx.stroke();
  }
}

async function exportData(format) {
  if (!state.target) return;
  const resp = await fetch(`/api/v1/export?format=${format}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      target: state.target,
      weights: state.weights,
      mode: state.scoringMode,
      filters: buildActiveFilters(),
      exclude_well_known: state.excludeWellKnown,
      top_k: 25,
    }),
  });
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `isotopos_analogs.${format}`;
  a.click();
  URL.revokeObjectURL(url);
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

  document.getElementById("btn-extract-coord").addEventListener("click", () => {
    const lat = parseFloat(document.getElementById("input-lat").value);
    const lon = parseFloat(document.getElementById("input-lon").value);
    if (!Number.isNaN(lat) && !Number.isNaN(lon)) {
      extractCoordinate(lat, lon);
    }
  });

  document.getElementById("planetary-picker-canvas").addEventListener("click", (e) => {
    const rect = e.target.getBoundingClientRect();
    const xFrac = (e.clientX - rect.left) / rect.width;
    const yFrac = (e.clientY - rect.top) / rect.height;
    const lat = 90.0 - yFrac * 180.0;
    const lon = xFrac * 360.0;
    extractCoordinate(lat, lon);
  });

  document.getElementById("scoring-mode-select").addEventListener("change", (e) => {
    state.scoringMode = e.target.value;
    runRank();
  });

  for (const id of ["flt-max-slope", "flt-min-temp", "flt-max-temp", "flt-min-aridity"]) {
    document.getElementById(id).addEventListener("change", scheduleRank);
  }

  document.getElementById("layer-variable-select").addEventListener("change", async (e) => {
    state.activeLayer = e.target.value;
    if (state.activeLayer.startsWith("dim:")) {
      await runRank();
    } else {
      await updateEarthMapLayers(true);
    }
  });

  document.getElementById("palette-select").addEventListener("change", (e) => {
    state.palette = e.target.value;
    updateLegendGradient();
    updateEarthMapLayers(false);
  });

  document.getElementById("basemap-select").addEventListener("change", (e) => {
    state.basemap = e.target.value;
    if (!state.map) return;
    state.map.setLayoutProperty(
      "gibs_bluemarble",
      "visibility",
      state.basemap === "gibs_bluemarble" ? "visible" : "none"
    );
    state.map.setLayoutProperty(
      "gibs_modis",
      "visibility",
      state.basemap === "gibs_modis" ? "visible" : "none"
    );
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
    renderRankedList();
  });

  document.getElementById("tab-h3").addEventListener("click", () => {
    state.activeTab = "h3";
    document.getElementById("tab-h3").classList.add("active");
    document.getElementById("tab-hotspots").classList.remove("active");
    renderRankedList();
  });

  document.getElementById("btn-export-csv").addEventListener("click", () => exportData("csv"));
  document.getElementById("btn-export-json").addEventListener("click", () => exportData("json"));
}

init();
