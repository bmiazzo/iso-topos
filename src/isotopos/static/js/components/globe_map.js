// 3D Earth Globe (MapLibre GL JS), basemap switching, ranked markers, hit-testing & layers

import { fetchRawParameter } from "../api.js";
import { PALETTES, state } from "../state.js";
import { escapeHtml, prefersReducedMotion, setSpinButtonState } from "../ui/dom.js";
import {
  buildFillColorExpression,
  buildFillOpacityExpression,
  buildOutlineColorExpression,
  buildOutlineOpacityExpression,
  computeLayerColorRange,
  normalizeLon180,
  updateLegendGradient,
  updateLegendLabels,
} from "./color_scale.js";

export { updateLegendGradient };

function shortPinTitle(name) {
  if (!name) return "";
  return name.length > 26 ? `${name.slice(0, 24)}…` : name;
}

let _cachedGeojsonRef = null;
let _siteCoordsById = new Map();
let _sitePropsById = new Map();
let _pushedDisplayVals = new Map();

function ensureGeojsonIndexes() {
  if (_cachedGeojsonRef !== state.earthGeojson) {
    _cachedGeojsonRef = state.earthGeojson;
    _siteCoordsById = new Map();
    _sitePropsById = new Map();
    _pushedDisplayVals = new Map();
    for (const f of state.earthGeojson?.features || []) {
      const id = f?.properties?.id;
      if (!id) continue;
      _sitePropsById.set(id, f.properties);
      const geom = f.geometry;
      if (!geom?.coordinates) continue;
      // Support both Polygon (coordinates[0]) and antimeridian MultiPolygon (coordinates[0][0])
      const ring = geom.type === "MultiPolygon" ? geom.coordinates[0]?.[0] : geom.coordinates[0];
      if (!ring?.length) continue;
      let sx = 0;
      let sy = 0;
      for (const pt of ring) {
        sx += pt[0];
        sy += pt[1];
      }
      _siteCoordsById.set(id, [sx / ring.length, sy / ring.length]);
    }
  }
}

function getSiteCoordsById() {
  ensureGeojsonIndexes();
  return _siteCoordsById;
}

function getSitePropsById() {
  ensureGeojsonIndexes();
  return _sitePropsById;
}

function resolveSiteCoords(siteId, explicitCoords) {
  if (explicitCoords && explicitCoords.length === 2) return explicitCoords;
  const fromRank = [
    ...(state.lastRankResponse?.top_h3_results || []),
    ...(state.lastRankResponse?.hotspot_results || []),
  ].find((r) => r.site.id === siteId);
  if (fromRank) return [fromRank.site.lon, fromRank.site.lat];
  return getSiteCoordsById().get(siteId) || null;
}

export function populateLayerSwitcher() {
  const sel = document.getElementById("layer-variable-select");
  if (!sel || !state.metadata) return;
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

function positionTooltipWithinStage(tooltipEl, stageW, stageH, tipW, tipH, point) {
  const left = Math.max(8, Math.min(stageW - tipW - 8, point.x + 14));
  const top = Math.max(8, Math.min(stageH - tipH - 8, point.y + 14));
  tooltipEl.style.transform = `translate3d(${left}px, ${top}px, 0)`;
}

export function highlightSelectedSiteOnMap(siteId, explicitCoords = null) {
  if (!state.map) return;
  const targetId = siteId || "";
  if (state.map.getLayer("earth-h3-selected")) {
    state.map.setFilter("earth-h3-selected", ["==", ["get", "id"], targetId]);
  }
  if (state.map.getLayer("earth-hotspots-selected")) {
    state.map.setFilter("earth-hotspots-selected", ["==", ["get", "id"], targetId]);
  }
  const beaconSrc = state.map.getSource("earth-selected-beacon");
  if (beaconSrc) {
    const coords = targetId ? resolveSiteCoords(targetId, explicitCoords) : null;
    beaconSrc.setData({
      type: "FeatureCollection",
      features: coords
        ? [{ type: "Feature", properties: { id: targetId }, geometry: { type: "Point", coordinates: coords } }]
        : [],
    });
  }
}

export function flyToSiteOnGlobe(lon, lat, zoom = 3.4, pauseSpin = true) {
  if (!state.map) return;
  if (pauseSpin && state.autoSpin) {
    state.autoSpin = false;
    setSpinButtonState(document.getElementById("btn-toggle-spin"), false);
  }
  state.userInteracting = true;
  clearTimeout(state.flyToTimer);
  const reduce = prefersReducedMotion();
  state.map.flyTo({ center: [lon, lat], zoom, ...(reduce ? { duration: 0 } : { speed: 1.15 }) });
  state.flyToTimer = setTimeout(() => {
    if (!state.pointerDown) state.userInteracting = false;
  }, reduce ? 100 : 2400);
}

export function initEarthMap({ onInspectSite }) {
  const style = {
    version: 8,
    glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
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

  const pausePointer = () => {
    state.pointerDown = true;
    state.userInteracting = true;
  };
  const resumePointer = () => {
    state.pointerDown = false;
    state.userInteracting = false;
    requestAutoSpinFrame();
  };
  map.on("mousedown", pausePointer);
  map.on("touchstart", pausePointer);
  map.on("wheel", () => {
    state.userInteracting = true;
    clearTimeout(map._wheelTimeout);
    map._wheelTimeout = setTimeout(() => {
      if (!state.pointerDown) {
        state.userInteracting = false;
        requestAutoSpinFrame();
      }
    }, 2200);
  });
  map.on("mouseup", resumePointer);
  map.on("touchend", resumePointer);
  map.on("zoomend", requestAutoSpinFrame);

  map.on("style.load", () => {
    map.setProjection({ type: state.isGlobe ? "globe" : "mercator" });
    requestAutoSpinFrame();
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
        "line-width": 2.8,
        "line-opacity": 0.98,
      },
    });

    // Top-K H3 Region Markers + Labels
    map.addSource("earth-top-h3", {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });

    map.addLayer({
      id: "earth-top-h3-halo",
      type: "circle",
      source: "earth-top-h3",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["get", "score"], 0.2, 10, 0.95, 19],
        "circle-color": "#2dd4bf",
        "circle-opacity": 0.26,
        "circle-blur": 0.6,
      },
    });

    map.addLayer({
      id: "earth-top-h3-pin",
      type: "circle",
      source: "earth-top-h3",
      paint: {
        "circle-radius": ["case", ["get", "is_top3"], 8.0, 6.0],
        "circle-color": ["case", ["get", "is_top3"], "#2dd4bf", "#0d9488"],
        "circle-stroke-width": 2.0,
        "circle-stroke-color": "#ffffff",
      },
    });

    map.addLayer({
      id: "earth-top-h3-label",
      type: "symbol",
      source: "earth-top-h3",
      layout: {
        "text-font": ["Open Sans Regular"],
        "text-field": ["get", "label"],
        "text-size": 11,
        "text-offset": [0, -1.35],
        "text-anchor": "bottom",
        "text-allow-overlap": false,
        "text-padding": 4,
        "symbol-sort-key": ["get", "rank"],
      },
      paint: {
        "text-color": "#ecfeff",
        "text-halo-color": "#040812",
        "text-halo-width": 1.8,
      },
    });

    // Named Analog Hotspots (Score-scaled + Labels)
    map.addSource("earth-hotspots", {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });

    map.addLayer({
      id: "earth-hotspots-glow",
      type: "circle",
      source: "earth-hotspots",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["get", "score"], 0.2, 9, 0.95, 17],
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
        "circle-radius": ["interpolate", ["linear"], ["get", "score"], 0.2, 4.8, 0.95, 8.6],
        "circle-color": ["case", ["get", "is_well_known"], "#f59e0b", "#38bdf8"],
        "circle-stroke-width": 1.7,
        "circle-stroke-color": "#ffffff",
      },
    });

    map.addLayer({
      id: "earth-hotspots-label",
      type: "symbol",
      source: "earth-hotspots",
      layout: {
        "text-font": ["Open Sans Regular"],
        "text-field": ["get", "label"],
        "text-size": 10.5,
        "text-offset": [0, 1.25],
        "text-anchor": "top",
        "text-allow-overlap": false,
        "text-padding": 4,
        "symbol-sort-key": ["+", 25, ["get", "rank"]],
      },
      paint: {
        "text-color": ["case", ["get", "is_well_known"], "#fde68a", "#bae6fd"],
        "text-halo-color": "#040812",
        "text-halo-width": 1.7,
      },
    });

    map.addLayer({
      id: "earth-hotspots-selected",
      type: "circle",
      source: "earth-hotspots",
      filter: ["==", ["get", "id"], ""],
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 1.5, 11.0, 5.0, 15.0],
        "circle-color": "rgba(56, 189, 248, 0.0)",
        "circle-stroke-width": 2.6,
        "circle-stroke-color": "#2dd4bf",
      },
    });

    // High-contrast beacon ring around whichever site (H3 or Hotspot) is selected
    map.addSource("earth-selected-beacon", {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });

    map.addLayer({
      id: "earth-selected-beacon-outer",
      type: "circle",
      source: "earth-selected-beacon",
      paint: {
        "circle-radius": 17,
        "circle-color": "rgba(45, 212, 191, 0.08)",
        "circle-stroke-width": 2.4,
        "circle-stroke-color": "#fde047",
      },
    });

    const tooltip = document.getElementById("hover-tooltip");
    const mapContainer = map.getContainer();
    const mapCanvas = map.getCanvas();
    const pinLayers = ["earth-hotspots-circle", "earth-top-h3-pin"];
    const interactiveLayers = ["earth-hotspots-circle", "earth-top-h3-pin", "earth-h3-fill"];

    let hoverRafId = 0;
    let pendingHoverEvent = null;
    let lastHoverKey = "";
    let lastCursor = "";
    let cachedTipW = 210;
    let cachedTipH = 64;
    let cachedStageW = mapContainer.clientWidth || 800;
    let cachedStageH = mapContainer.clientHeight || 600;

    const setCursor = (cursor) => {
      if (lastCursor !== cursor) {
        lastCursor = cursor;
        mapCanvas.style.cursor = cursor;
      }
    };

    const hideTooltip = () => {
      pendingHoverEvent = null;
      if (hoverRafId) {
        cancelAnimationFrame(hoverRafId);
        hoverRafId = 0;
      }
      setCursor("");
      if (lastHoverKey !== "") {
        lastHoverKey = "";
        tooltip.classList.add("hidden");
      }
    };

    const showTooltip = (key, html, point, cursor) => {
      setCursor(cursor);
      if (lastHoverKey !== key) {
        lastHoverKey = key;
        tooltip.innerHTML = html;
        tooltip.classList.remove("hidden");
        cachedTipW = tooltip.offsetWidth || 210;
        cachedTipH = tooltip.offsetHeight || 64;
        cachedStageW = mapContainer.clientWidth || 800;
        cachedStageH = mapContainer.clientHeight || 600;
      }
      positionTooltipWithinStage(tooltip, cachedStageW, cachedStageH, cachedTipW, cachedTipH, point);
    };

    const processHoverFrame = () => {
      hoverRafId = 0;
      const e = pendingHoverEvent;
      pendingHoverEvent = null;
      if (!e || state.pointerDown || map.isMoving()) {
        return;
      }

      const pinHits = map.queryRenderedFeatures(e.point, { layers: pinLayers });
      if (pinHits.length) {
        const top = pinHits[0];
        const p = top.properties;
        if (top.layer.id === "earth-hotspots-circle") {
          const kind = p.is_well_known ? "Well-Known Baseline" : "Novel Hotspot";
          const key = `hs:${p.id}:${p.score_pct}`;
          const html =
            `<strong>${escapeHtml(p.name)}</strong><br/>` +
            `${escapeHtml(p.country || kind)}<br/>` +
            `Similarity: <b>${escapeHtml(p.score_pct)}%</b>`;
          showTooltip(key, html, e.point, "pointer");
          return;
        }
        const key = `pin:${p.id}:${p.rank}:${p.score_pct}`;
        const html =
          `<strong>#${escapeHtml(p.rank)} ${escapeHtml(p.name)}</strong><br/>` +
          `${escapeHtml(p.country)} · Top H3 Region<br/>` +
          `Similarity: <b>${escapeHtml(p.score_pct)}%</b>`;
        showTooltip(key, html, e.point, "pointer");
        return;
      }

      let props = null;
      if (typeof window !== "undefined" && window.h3?.latLngToCell && e.lngLat) {
        const h3Id = window.h3.latLngToCell(e.lngLat.lat, normalizeLon180(e.lngLat.lng), 4);
        props = getSitePropsById().get(h3Id) || null;
      } else {
        const h3Hits = map.queryRenderedFeatures(e.point, { layers: ["earth-h3-fill"] });
        props = h3Hits.length ? h3Hits[0].properties : null;
      }

      if (!props) {
        hideTooltip();
        return;
      }

      const val = state.cellDisplayValues[props.id] ?? -999999;
      const isRaw = state.activeLayer.startsWith("raw:");
      const cutoff = isRaw ? -99999 : state.minScoreFilter;

      if (!isRaw && state.excludeWellKnown && props.is_well_known) {
        const key = `excl:${props.id}`;
        const html =
          `<strong>${escapeHtml(props.country || props.name)}</strong><br/>` +
          `Excluded Baseline Region`;
        showTooltip(key, html, e.point, "");
        return;
      }

      if (val <= -99999 || val < cutoff) {
        hideTooltip();
        return;
      }

      let unitLabel = "%";
      if (isRaw) {
        const param = state.metadata.parameters.find((pm) => pm.id === state.activeLayer.slice(4));
        unitLabel = param ? ` ${param.unit}` : "";
      }
      const place = props.country && props.country !== props.region
        ? `${props.country} (${props.region})`
        : props.region;
      const formattedVal = Number(val).toFixed(1);
      const key = `h3:${props.id}:${formattedVal}:${unitLabel}`;
      const html =
        `<strong>${escapeHtml(props.name)}</strong><br/>` +
        `${escapeHtml(place)}<br/>` +
        `Value: <b>${escapeHtml(formattedVal)}${escapeHtml(unitLabel)}</b>`;
      showTooltip(key, html, e.point, "pointer");
    };

    map.on("mousedown", hideTooltip);
    map.on("dragstart", hideTooltip);
    map.on("movestart", hideTooltip);
    map.on("mouseout", hideTooltip);
    map.on("resize", () => {
      cachedStageW = mapContainer.clientWidth || 800;
      cachedStageH = mapContainer.clientHeight || 600;
    });

    map.on("mousemove", (e) => {
      if (state.pointerDown || map.isMoving()) {
        hideTooltip();
        return;
      }
      pendingHoverEvent = e;
      if (!hoverRafId) {
        hoverRafId = requestAnimationFrame(processHoverFrame);
      }
    });

    map.on("click", (e) => {
      const hits = map.queryRenderedFeatures(e.point, { layers: interactiveLayers });
      if (!hits.length) return;
      const top = hits[0];
      if (top.layer.id === "earth-hotspots-circle" || top.layer.id === "earth-top-h3-pin") {
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
    highlightSelectedSiteOnMap(state.selectedSiteId);
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

let _spinRafId = 0;
let _spinLastTime = 0;
let _spinListenersBound = false;

function shouldSpinEarth() {
  return Boolean(
    !document.hidden &&
      state.map &&
      state.isGlobe &&
      state.autoSpin &&
      !state.userInteracting &&
      !state.pointerDown &&
      state.map.getZoom() < 2.8
  );
}

function spinStep(now) {
  _spinRafId = 0;
  if (!shouldSpinEarth()) return;
  const dt = Math.min(0.1, (now - _spinLastTime) / 1000.0);
  _spinLastTime = now;
  const center = state.map.getCenter();
  center.lng = ((center.lng + dt * 2.4 + 180) % 360) - 180;
  state.map.setCenter(center);
  _spinRafId = requestAnimationFrame(spinStep);
}

export function requestAutoSpinFrame() {
  if (!_spinRafId && shouldSpinEarth()) {
    _spinLastTime = performance.now();
    _spinRafId = requestAnimationFrame(spinStep);
  }
}

export function startAutoSpinLoop() {
  if (!_spinListenersBound && typeof document !== "undefined") {
    _spinListenersBound = true;
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) requestAutoSpinFrame();
    });
  }
  requestAutoSpinFrame();
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
  const { cell_scores, cell_dimension_scores, hotspot_results, top_h3_results } = state.lastRankResponse;
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
      if (rawMap) {
        val = rawMap[id] ?? -999999;
      } else if (id in cell_scores) {
        if (layerKey === "overall_score") {
          val = cell_scores[id] * 100.0;
        } else if (dimId) {
          const sub = cell_dimension_scores[id]?.[dimId];
          val = sub === null || sub === undefined ? -999999 : sub * 100.0;
        }
      }
      state.cellDisplayValues[id] = val;
      if (_pushedDisplayVals.get(id) !== val) {
        _pushedDisplayVals.set(id, val);
        state.map.setFeatureState({ source: "earth-h3", id }, { display_val: val });
      }
    }
  }

  const effectiveCutoff = isScoreLayer ? state.minScoreFilter : -99999;
  const { minVal, midVal, maxVal, rawMin, rawMax, isClipped, validCount } = computeLayerColorRange({
    features: state.earthGeojson.features,
    cellDisplayValues: state.cellDisplayValues,
    isScoreLayer,
    effectiveCutoff,
    scaleMode: state.scaleMode,
    paramSpec,
  });

  if (layerKey.startsWith("dim:") && validCount === 0 && Object.keys(cell_scores).length > 0) {
    legendTitle = `${legendTitle} — N/A (0% weights)`;
  }

  updateLegendLabels({
    legendTitle,
    minVal,
    midVal,
    maxVal,
    rawMin,
    rawMax,
    isClipped,
    isScoreLayer,
    scaleMode: state.scaleMode,
  });

  const paletteStops = PALETTES[state.palette] || PALETTES.bioluminescent;
  const valExpr = ["coalesce", ["feature-state", "display_val"], -999999];
  const dimWellKnown = isScoreLayer && state.excludeWellKnown;

  const colorExpr = buildFillColorExpression({
    valExpr,
    effectiveCutoff,
    paletteStops,
    minVal,
    maxVal,
    scaleMode: state.scaleMode,
    dimWellKnown,
  });
  const opacityExpr = buildFillOpacityExpression({
    valExpr,
    isScoreLayer,
    effectiveCutoff,
    hexOpacity: state.hexOpacity,
    minVal,
    maxVal,
    dimWellKnown,
  });
  const outlineOpacityExpr = buildOutlineOpacityExpression({
    isScoreLayer,
  });
  const outlineColorExpr = buildOutlineColorExpression({
    valExpr,
    isScoreLayer,
    effectiveCutoff,
  });

  state.map.setPaintProperty("earth-h3-fill", "fill-color", colorExpr);
  state.map.setPaintProperty("earth-h3-fill", "fill-opacity", opacityExpr);
  state.map.setPaintProperty("earth-h3-outline", "line-color", outlineColorExpr);
  state.map.setPaintProperty("earth-h3-outline", "line-opacity", outlineOpacityExpr);

  const minPinScore = isScoreLayer ? state.minScoreFilter : 0;

  // Update Top-K H3 region pins
  const h3Features = (top_h3_results || [])
    .filter((r) => r.overall_score * 100 >= minPinScore)
    .map((r) => {
      const scorePct = Math.round(r.overall_score * 100);
      return {
        type: "Feature",
        properties: {
          id: r.site.id,
          name: r.site.name,
          country: r.site.country || r.site.region,
          rank: r.rank,
          score: r.overall_score,
          score_pct: scorePct,
          is_top3: r.rank <= 3,
          label: `#${r.rank} ${shortPinTitle(r.site.name)} (${scorePct}%)`,
        },
        geometry: {
          type: "Point",
          coordinates: [r.site.lon, r.site.lat],
        },
      };
    });
  state.map.getSource("earth-top-h3")?.setData({
    type: "FeatureCollection",
    features: h3Features,
  });

  // Update Named Hotspot markers (respecting Min Score Spotlight & toggle)
  const hsFeatures = state.showHotspots
    ? (hotspot_results || [])
        .filter((r) => r.overall_score * 100 >= minPinScore)
        .map((r, idx) => {
          const scorePct = Math.round(r.overall_score * 100);
          return {
            type: "Feature",
            properties: {
              id: r.site.id,
              name: r.site.name,
              country: r.site.country || r.site.region,
              rank: idx + 1,
              is_well_known: r.site.is_well_known,
              score: r.overall_score,
              score_pct: scorePct,
              label: `${shortPinTitle(r.site.name)} (${scorePct}%)`,
            },
            geometry: {
              type: "Point",
              coordinates: [r.site.lon, r.site.lat],
            },
          };
        })
    : [];

  state.map.getSource("earth-hotspots")?.setData({
    type: "FeatureCollection",
    features: hsFeatures,
  });
}
