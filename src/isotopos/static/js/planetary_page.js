// Dedicated /planetary 3D Moon & Mars Target Explorer

import { extractTarget, fetchMetadata } from "./api.js";
import { normalizeLon180, samplePaletteRgb } from "./components/color_scale.js";
import { initStarfield } from "./components/starfield.js";
import { PALETTES } from "./state.js";
import { escapeHtml, prefersReducedMotion, setButtonPressed, setSpinButtonState } from "./ui/dom.js";

const PLANETARY_TILES = {
  moon: {
    url: "https://cartocdn-gusc.global.ssl.fastly.net/opmbuilder/api/v1/map/named/opm-moon-basemap-v0-1/all/{z}/{x}/{y}.png",
    attribution: "OpenPlanetaryMap Moon / NASA LRO LOLA",
    bgColor: "#141821",
  },
  mars: {
    url: "https://cartocdn-gusc.global.ssl.fastly.net/opmbuilder/api/v1/map/named/opm-mars-basemap-v0-2/all/{z}/{x}/{y}.png",
    attribution: "OpenPlanetaryMap Mars / NASA MGS MOLA",
    bgColor: "#26120c",
  },
};

const IMAGE_MERCATOR_BOUNDS = [
  [-180, 85.05112878],
  [180, 85.05112878],
  [180, -85.05112878],
  [-180, -85.05112878],
];

const plState = {
  metadata: null,
  body: "moon",
  presetId: null,
  target: null,
  overlayParam: "none",
  palette: "bioluminescent",
  isGlobe: true,
  autoSpin: !prefersReducedMotion(),
  userInteracting: false,
  pointerDown: false,
  map: null,
  mapReady: false,
  gridCache: {},
  shadedUrlCache: {},
  activeSlice: null,
};

async function fetchPlanetaryGridSlice(body, paramId) {
  const key = `${body}:${paramId}`;
  if (plState.gridCache[key]) return plState.gridCache[key];
  const resp = await fetch(`/api/v1/planetary-grid/${encodeURIComponent(body)}/parameter/${encodeURIComponent(paramId)}`);
  if (!resp.ok) throw new Error(`Grid slice HTTP ${resp.status}`);
  const data = await resp.json();
  plState.gridCache[key] = data;
  return data;
}

function bilinearSampleSlice(slice, lat, lon180) {
  const step = Number(slice.step_deg);
  const nLat = slice.lats.length;
  const nLon = slice.lons.length;
  const clampedLat = Math.max(-90, Math.min(90, lat));
  const lon360 = ((lon180 % 360) + 360) % 360;

  const yf = (clampedLat + 90) / step;
  const i0 = Math.min(nLat - 2, Math.max(0, Math.floor(yf)));
  const i1 = i0 + 1;
  const ty = Math.max(0, Math.min(1, yf - i0));

  const xf = lon360 / step;
  const j0 = Math.floor(xf) % nLon;
  const j1 = (j0 + 1) % nLon;
  const tx = xf - Math.floor(xf);

  const v00 = slice.values[i0][j0];
  const v10 = slice.values[i0][j1];
  const v01 = slice.values[i1][j0];
  const v11 = slice.values[i1][j1];
  return (1 - ty) * ((1 - tx) * v00 + tx * v10) + ty * ((1 - tx) * v01 + tx * v11);
}

const _paletteLutCache = new Map();

function getPaletteLut(paletteName) {
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

function renderSliceToMercatorDataUrl(slice, paletteName, alpha = 210) {
  const w = 360;
  const h = 180;
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  const img = ctx.createImageData(w, h);
  const data = img.data;

  const step = Number(slice.step_deg);
  const nLat = slice.lats.length;
  const nLon = slice.lons.length;
  const values = slice.values;

  let minV = Infinity;
  let maxV = -Infinity;
  for (let i = 0; i < nLat; i++) {
    const row = values[i];
    for (let j = 0; j < nLon; j++) {
      const v = row[j];
      if (v < minV) minV = v;
      if (v > maxV) maxV = v;
    }
  }
  const invSpan = 255 / Math.max(1e-6, maxV - minV);
  const lut = getPaletteLut(paletteName);

  // Precompute x-column lookup indices & weights once (360 vs 64,800)
  const j0Arr = new Int32Array(w);
  const j1Arr = new Int32Array(w);
  const txArr = new Float32Array(w);
  for (let px = 0; px < w; px++) {
    const lon360 = ((-180 + (360 * (px + 0.5)) / w) % 360 + 360) % 360;
    const xf = lon360 / step;
    const j0 = Math.floor(xf) % nLon;
    j0Arr[px] = j0;
    j1Arr[px] = (j0 + 1) % nLon;
    txArr[px] = xf - Math.floor(xf);
  }

  for (let py = 0; py < h; py++) {
    const mercY = Math.PI * (1 - (2 * (py + 0.5)) / h);
    const lat = Math.max(-90, Math.min(90, (2 * Math.atan(Math.exp(mercY)) - Math.PI / 2) * (180 / Math.PI)));
    const yf = (lat + 90) / step;
    const i0 = Math.min(nLat - 2, Math.max(0, Math.floor(yf)));
    const ty = Math.max(0, Math.min(1, yf - i0));
    const oneMinusTy = 1 - ty;
    const row0 = values[i0];
    const row1 = values[i0 + 1];
    let idx = py * w * 4;

    for (let px = 0; px < w; px++) {
      const j0 = j0Arr[px];
      const j1 = j1Arr[px];
      const tx = txArr[px];
      const v0 = row0[j0] + tx * (row0[j1] - row0[j0]);
      const v1 = row1[j0] + tx * (row1[j1] - row1[j0]);
      const val = oneMinusTy * v0 + ty * v1;
      const lutIdx = Math.max(0, Math.min(255, ((val - minV) * invSpan + 0.5) | 0)) * 3;
      data[idx] = lut[lutIdx];
      data[idx + 1] = lut[lutIdx + 1];
      data[idx + 2] = lut[lutIdx + 2];
      data[idx + 3] = alpha;
      idx += 4;
    }
  }
  ctx.putImageData(img, 0, 0);
  return { url: canvas.toDataURL("image/png"), minV, maxV };
}

function makeSolidFallbackDataUrl(body) {
  const canvas = document.createElement("canvas");
  canvas.width = 4;
  canvas.height = 4;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = PLANETARY_TILES[body].bgColor;
  ctx.fillRect(0, 0, 4, 4);
  return canvas.toDataURL("image/png");
}

function populateOverlayDropdown() {
  const sel = document.getElementById("pl-overlay-select");
  if (!sel || !plState.metadata) return;
  sel.innerHTML = "";
  const noneOpt = document.createElement("option");
  noneOpt.value = "none";
  noneOpt.textContent = "Overlay: Surface Imagery Only";
  sel.appendChild(noneOpt);
  for (const p of plState.metadata.parameters) {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = `Overlay: ${p.label} (${p.unit})`;
    sel.appendChild(opt);
  }
  sel.value = plState.overlayParam;
}

function updateLegendUI(paramSpec, minV, maxV) {
  const card = document.getElementById("pl-legend-card");
  if (!card) return;
  if (!paramSpec) {
    card.classList.add("hidden");
    return;
  }
  card.classList.remove("hidden");
  const fmt = (v) => (Math.abs(v) >= 100 ? Math.round(v).toString() : v.toFixed(1));
  document.getElementById("pl-legend-title").textContent = `${paramSpec.label} (${paramSpec.unit})`;
  document.getElementById("pl-legend-min").textContent = fmt(minV);
  document.getElementById("pl-legend-mid").textContent = fmt((minV + maxV) / 2);
  document.getElementById("pl-legend-max").textContent = fmt(maxV);
  document.getElementById("pl-legend-range").textContent = `${fmt(minV)}–${fmt(maxV)}`;

  const stops = PALETTES[plState.palette] || PALETTES.bioluminescent;
  document.getElementById("pl-legend-bar").style.background =
    `linear-gradient(90deg, ${stops.map(([t, c]) => `${c} ${Math.round(t * 100)}%`).join(", ")})`;
}

async function refreshOverlayLayer() {
  if (!plState.map || !plState.mapReady) return;
  const src = plState.map.getSource("pl-data-overlay");
  if (!src) return;

  if (plState.overlayParam === "none") {
    plState.activeSlice = null;
    plState.map.setPaintProperty("pl-data-overlay-layer", "raster-opacity", 0);
    updateLegendUI(null, 0, 0);
    return;
  }

  try {
    const slice = await fetchPlanetaryGridSlice(plState.body, plState.overlayParam);
    plState.activeSlice = slice;
    const { url, minV, maxV } = renderSliceToMercatorDataUrl(slice, plState.palette, 230);
    src.updateImage({ url, coordinates: IMAGE_MERCATOR_BOUNDS });
    plState.map.setPaintProperty("pl-data-overlay-layer", "raster-opacity", 0.65);
    const paramSpec = plState.metadata.parameters.find((p) => p.id === plState.overlayParam);
    updateLegendUI(paramSpec, minV, maxV);
  } catch (err) {
    console.warn("Planetary overlay fetch failed:", err);
  }
}

async function refreshFallbackShadedTerrain() {
  if (!plState.map || !plState.mapReady) return;
  const src = plState.map.getSource("pl-fallback-relief");
  if (!src) return;
  const body = plState.body;
  try {
    let url = plState.shadedUrlCache[body];
    if (!url) {
      const slice = await fetchPlanetaryGridSlice(body, "elevation_m");
      const pal = body === "mars" ? "magma" : "viridis";
      url = renderSliceToMercatorDataUrl(slice, pal, 255).url;
      plState.shadedUrlCache[body] = url;
    }
    if (plState.body === body) {
      src.updateImage({ url, coordinates: IMAGE_MERCATOR_BOUNDS });
    }
  } catch {
    // Keep solid fallback if API unavailable
  }
}

function updateBasemapVisibility() {
  if (!plState.map || !plState.mapReady) return;
  plState.map.setLayoutProperty("opm-moon-layer", "visibility", plState.body === "moon" ? "visible" : "none");
  plState.map.setLayoutProperty("opm-mars-layer", "visibility", plState.body === "mars" ? "visible" : "none");
  refreshFallbackShadedTerrain();
}

function updateMarkersAndList() {
  if (!plState.metadata) return;
  const presets = plState.metadata.presets.filter((p) => p.body === plState.body);
  document.getElementById("pl-mission-count").textContent = String(presets.length);

  const listEl = document.getElementById("pl-mission-list");
  listEl.innerHTML = "";
  for (const p of presets) {
    const btn = document.createElement("button");
    btn.type = "button";
    const selected = p.id === plState.presetId;
    btn.className = `mission-pin-item ${selected ? "selected" : ""}`;
    btn.innerHTML = `
      <span class="mission-pin-info">
        <span class="mission-pin-name">${escapeHtml(p.name)}</span>
        <small>${escapeHtml(p.mission_context || "")}</small>
      </span>
      <small class="mono-num">${p.lat.toFixed(1)}°, ${normalizeLon180(p.lon).toFixed(1)}°</small>
    `;
    btn.addEventListener("click", () => selectPreset(p.id, true));
    listEl.appendChild(btn);
  }

  if (plState.map && plState.mapReady) {
    const pinSrc = plState.map.getSource("pl-mission-pins");
    if (pinSrc) {
      pinSrc.setData({
        type: "FeatureCollection",
        features: presets.map((p) => ({
          type: "Feature",
          properties: {
            id: p.id,
            name: p.name,
            is_selected: p.id === plState.presetId,
          },
          geometry: {
            type: "Point",
            coordinates: [normalizeLon180(p.lon), p.lat],
          },
        })),
      });
    }

    const selSrc = plState.map.getSource("pl-selected-point");
    if (selSrc && plState.target) {
      selSrc.setData({
        type: "FeatureCollection",
        features: [
          {
            type: "Feature",
            properties: { name: plState.target.name },
            geometry: {
              type: "Point",
              coordinates: [normalizeLon180(plState.target.lon), plState.target.lat],
            },
          },
        ],
      });
    }
  }
}

function renderTargetDetails() {
  const t = plState.target;
  if (!t || !plState.metadata) return;

  document.getElementById("pl-target-name").textContent = t.name;
  document.getElementById("pl-target-coords").textContent =
    `${t.body.toUpperCase()} · ${t.lat.toFixed(2)}° lat, ${normalizeLon180(t.lon).toFixed(2)}° lon`;
  document.getElementById("pl-target-notes").textContent = t.notes || "";

  document.getElementById("pl-input-lat").value = t.lat.toFixed(2);
  document.getElementById("pl-input-lon").value = normalizeLon180(t.lon).toFixed(2);

  const badge = document.getElementById("pl-target-badge");
  const modePill = document.getElementById("pl-param-mode");
  if (t.is_extrapolated) {
    badge.textContent = "Extrapolated Target";
    badge.className = "badge badge-warn";
    modePill.textContent = "Grid Interpolated";
    modePill.className = "summary-pill pill-warn";
  } else {
    badge.textContent = "Preset Exact";
    badge.className = "badge badge-neutral";
    modePill.textContent = "Mission Exact";
    modePill.className = "summary-pill pill-accent";
  }

  const extrapSet = new Set(t.extrapolated_parameters || []);
  const tbody = document.getElementById("pl-param-tbody");
  tbody.innerHTML = "";
  for (const p of plState.metadata.parameters) {
    const prov = plState.body === "moon" ? p.moon_provenance : p.mars_provenance;
    const val = t.parameters[p.id];
    const extrapTag = extrapSet.has(p.id) ? " · interp." : "";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(p.label)}<br/><small>${escapeHtml(p.unit)}</small></td>
      <td class="mono-num"><b>${escapeHtml(Number(val).toFixed(2))}</b></td>
      <td><a href="${escapeHtml(prov.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(prov.agency_mission)}</a>${escapeHtml(extrapTag)}</td>
    `;
    tbody.appendChild(tr);
  }
}

async function selectPreset(presetId, fly = true) {
  const target = await extractTarget({ preset_id: presetId });
  plState.body = target.body;
  plState.presetId = presetId;
  plState.target = target;
  setButtonPressed(document.getElementById("pl-btn-moon"), target.body === "moon");
  setButtonPressed(document.getElementById("pl-btn-mars"), target.body === "mars");
  updateBasemapVisibility();
  updateMarkersAndList();
  renderTargetDetails();
  await refreshOverlayLayer();
  if (fly && plState.map) {
    plState.userInteracting = true;
    plState.map.flyTo({
      center: [normalizeLon180(target.lon), target.lat],
      zoom: 2.6,
      ...(prefersReducedMotion() ? { duration: 0 } : {}),
    });
    setTimeout(() => {
      if (!plState.pointerDown) plState.userInteracting = false;
    }, 2200);
  }
}

async function extractCustomCoord(lat, lon, fly = false) {
  const clampedLat = Math.max(-90, Math.min(90, lat));
  const lon180 = normalizeLon180(lon);
  const target = await extractTarget({ body: plState.body, lat: clampedLat, lon: lon180 });
  plState.presetId = null;
  plState.target = target;
  updateMarkersAndList();
  renderTargetDetails();
  if (fly && plState.map) {
    plState.userInteracting = true;
    plState.map.flyTo({
      center: [lon180, clampedLat],
      zoom: 2.4,
      ...(prefersReducedMotion() ? { duration: 0 } : {}),
    });
    setTimeout(() => {
      if (!plState.pointerDown) plState.userInteracting = false;
    }, 2000);
  }
}

function switchBody(nextBody) {
  if (plState.body === nextBody) return;
  plState.body = nextBody;
  setButtonPressed(document.getElementById("pl-btn-moon"), nextBody === "moon");
  setButtonPressed(document.getElementById("pl-btn-mars"), nextBody === "mars");
  const first = plState.metadata.presets.find((p) => p.body === nextBody);
  if (first) {
    selectPreset(first.id, true);
  } else {
    updateBasemapVisibility();
    refreshOverlayLayer();
  }
}

function initPlanetaryMap() {
  const style = {
    version: 8,
    glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
    projection: { type: "globe" },
    sky: {
      "atmosphere-blend": 0.0,
    },
    sources: {
      "pl-fallback-relief": {
        type: "image",
        url: makeSolidFallbackDataUrl(plState.body),
        coordinates: IMAGE_MERCATOR_BOUNDS,
      },
      "opm-moon": {
        type: "raster",
        tiles: [PLANETARY_TILES.moon.url],
        tileSize: 256,
        maxzoom: 6,
        attribution: PLANETARY_TILES.moon.attribution,
      },
      "opm-mars": {
        type: "raster",
        tiles: [PLANETARY_TILES.mars.url],
        tileSize: 256,
        maxzoom: 6,
        attribution: PLANETARY_TILES.mars.attribution,
      },
      "pl-data-overlay": {
        type: "image",
        url: makeSolidFallbackDataUrl(plState.body),
        coordinates: IMAGE_MERCATOR_BOUNDS,
      },
    },
    layers: [
      { id: "bg", type: "background", paint: { "background-color": "rgba(4, 8, 18, 0.0)" } },
      { id: "pl-fallback-layer", type: "raster", source: "pl-fallback-relief", paint: { "raster-opacity": 0.92 } },
      { id: "opm-moon-layer", type: "raster", source: "opm-moon" },
      { id: "opm-mars-layer", type: "raster", source: "opm-mars", layout: { visibility: "none" } },
      { id: "pl-data-overlay-layer", type: "raster", source: "pl-data-overlay", paint: { "raster-opacity": 0.0 } },
    ],
  };

  const map = new maplibregl.Map({
    container: "planetary-map",
    style,
    center: [plState.target ? normalizeLon180(plState.target.lon) : 23, plState.target ? plState.target.lat : 0],
    zoom: 1.65,
  });
  map.addControl(new maplibregl.NavigationControl(), "top-right");

  map.on("mousedown", () => {
    plState.pointerDown = true;
    plState.userInteracting = true;
  });
  map.on("mouseup", () => {
    plState.pointerDown = false;
    plState.userInteracting = false;
    requestPlanetarySpinFrame();
  });
  map.on("touchstart", () => {
    plState.pointerDown = true;
    plState.userInteracting = true;
  });
  map.on("touchend", () => {
    plState.pointerDown = false;
    plState.userInteracting = false;
    requestPlanetarySpinFrame();
  });
  map.on("zoomend", () => requestPlanetarySpinFrame());
  map.on("style.load", () => {
    map.setProjection({ type: plState.isGlobe ? "globe" : "mercator" });
    requestPlanetarySpinFrame();
  });

  map.on("load", () => {
    map.addSource("pl-mission-pins", {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });
    map.addLayer({
      id: "pl-mission-pins-circle",
      type: "circle",
      source: "pl-mission-pins",
      paint: {
        "circle-radius": ["case", ["get", "is_selected"], 8, 5.5],
        "circle-color": ["case", ["get", "is_selected"], "#fbbf24", "#e2e8f0"],
        "circle-stroke-width": 1.8,
        "circle-stroke-color": "#09101d",
      },
    });
    map.addLayer({
      id: "pl-mission-pins-label",
      type: "symbol",
      source: "pl-mission-pins",
      layout: {
        "text-font": ["Open Sans Regular"],
        "text-field": ["get", "name"],
        "text-size": 11,
        "text-offset": [0, 1.15],
        "text-anchor": "top",
        "text-allow-overlap": false,
      },
      paint: {
        "text-color": ["case", ["get", "is_selected"], "#fde68a", "#e2e8f0"],
        "text-halo-color": "#060b16",
        "text-halo-width": 1.4,
      },
    });

    map.addSource("pl-selected-point", {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });
    map.addLayer({
      id: "pl-selected-ring",
      type: "circle",
      source: "pl-selected-point",
      paint: {
        "circle-radius": 13,
        "circle-color": "rgba(56, 189, 248, 0.14)",
        "circle-stroke-width": 2.4,
        "circle-stroke-color": "#38bdf8",
      },
    });

    map.on("mousemove", (e) => {
      const lat = e.lngLat.lat;
      const lon = normalizeLon180(e.lngLat.lng);
      let extra = "";
      if (plState.activeSlice) {
        const val = bilinearSampleSlice(plState.activeSlice, lat, lon);
        extra = ` · ${plState.overlayParam}: ${val.toFixed(1)}`;
      }
      document.getElementById("pl-cursor-pill").textContent =
        `${plState.body.toUpperCase()} · ${lat.toFixed(2)}°, ${lon.toFixed(2)}°${extra}`;
    });

    map.on("click", (e) => {
      const hits = map.queryRenderedFeatures(e.point, { layers: ["pl-mission-pins-circle"] });
      if (hits.length) {
        selectPreset(hits[0].properties.id, true);
      } else {
        extractCustomCoord(e.lngLat.lat, e.lngLat.lng, false);
      }
    });

    plState.mapReady = true;
    updateBasemapVisibility();
    updateMarkersAndList();
    refreshOverlayLayer();
    requestPlanetarySpinFrame();
  });

  plState.map = map;
  if (typeof document !== "undefined") {
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) requestPlanetarySpinFrame();
    });
  }
  requestPlanetarySpinFrame();
}

let _plSpinRafId = 0;
let _plSpinLastT = 0;

function shouldSpinPlanetary() {
  return Boolean(
    !document.hidden &&
      plState.map &&
      plState.mapReady &&
      plState.isGlobe &&
      plState.autoSpin &&
      !plState.userInteracting &&
      !plState.pointerDown &&
      plState.map.getZoom() < 2.2
  );
}

function planetarySpinTick(now) {
  _plSpinRafId = 0;
  if (!shouldSpinPlanetary()) return;
  const dt = Math.min(0.1, (now - _plSpinLastT) / 1000);
  _plSpinLastT = now;
  const c = plState.map.getCenter();
  c.lng = normalizeLon180(c.lng + dt * 2.0);
  plState.map.setCenter(c);
  _plSpinRafId = requestAnimationFrame(planetarySpinTick);
}

function requestPlanetarySpinFrame() {
  if (!_plSpinRafId && shouldSpinPlanetary()) {
    _plSpinLastT = performance.now();
    _plSpinRafId = requestAnimationFrame(planetarySpinTick);
  }
}

function bindEvents() {
  document.getElementById("pl-btn-moon").addEventListener("click", () => switchBody("moon"));
  document.getElementById("pl-btn-mars").addEventListener("click", () => switchBody("mars"));

  document.getElementById("pl-overlay-select").addEventListener("change", (e) => {
    plState.overlayParam = e.target.value;
    refreshOverlayLayer();
  });
  document.getElementById("pl-palette-select").addEventListener("change", (e) => {
    plState.palette = e.target.value;
    if (plState.overlayParam !== "none") refreshOverlayLayer();
  });

  document.getElementById("pl-btn-spin").addEventListener("click", (e) => {
    plState.autoSpin = !plState.autoSpin;
    setSpinButtonState(e.target, plState.autoSpin);
    requestPlanetarySpinFrame();
  });

  document.getElementById("pl-btn-proj").addEventListener("click", (e) => {
    plState.isGlobe = !plState.isGlobe;
    plState.map?.setProjection({ type: plState.isGlobe ? "globe" : "mercator" });
    e.target.textContent = plState.isGlobe ? "3D Globe: ON" : "2D Map: ON";
    e.target.setAttribute("aria-pressed", plState.isGlobe ? "true" : "false");
    requestPlanetarySpinFrame();
  });

  document.getElementById("pl-extract-btn").addEventListener("click", () => {
    const lat = parseFloat(document.getElementById("pl-input-lat").value);
    const lon = parseFloat(document.getElementById("pl-input-lon").value);
    if (!Number.isNaN(lat) && !Number.isNaN(lon)) {
      extractCustomCoord(lat, lon, true);
    }
  });

  document.getElementById("pl-confirm-btn").addEventListener("click", () => {
    if (!plState.target) return;
    if (plState.presetId) {
      window.location.href = `/?preset=${encodeURIComponent(plState.presetId)}`;
    } else {
      window.location.href =
        `/?body=${encodeURIComponent(plState.body)}&lat=${plState.target.lat.toFixed(3)}&lon=${normalizeLon180(plState.target.lon).toFixed(3)}`;
    }
  });
}

async function init() {
  initStarfield();
  setSpinButtonState(document.getElementById("pl-btn-spin"), plState.autoSpin);
  plState.metadata = await fetchMetadata();
  populateOverlayDropdown();
  bindEvents();

  const params = new URLSearchParams(window.location.search);
  const presetParam = params.get("preset");
  const bodyParam = params.get("body");
  const latParam = parseFloat(params.get("lat"));
  const lonParam = parseFloat(params.get("lon"));

  if (bodyParam === "moon" || bodyParam === "mars") {
    plState.body = bodyParam;
  }

  initPlanetaryMap();

  if (presetParam && plState.metadata.presets.some((p) => p.id === presetParam)) {
    await selectPreset(presetParam, true);
  } else if (!Number.isNaN(latParam) && !Number.isNaN(lonParam)) {
    setButtonPressed(document.getElementById("pl-btn-moon"), plState.body === "moon");
    setButtonPressed(document.getElementById("pl-btn-mars"), plState.body === "mars");
    await extractCustomCoord(latParam, lonParam, true);
  } else {
    const first = plState.metadata.presets.find((p) => p.body === plState.body) || plState.metadata.presets[0];
    if (first) await selectPreset(first.id, true);
  }
}

init();
