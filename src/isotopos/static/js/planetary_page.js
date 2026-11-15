// Dedicated /planetary 3D Moon & Mars Target Explorer (CesiumJS, full -90..+90 polar coverage)

import { extractTarget, fetchMetadata } from "./api.js";
import {
  bindCesiumCameraInteraction,
  cameraHeightToApproxZoom,
  createAutoSpinController,
  createCesiumViewer,
  flyToLatLon,
  makePinDataUrl,
  pickGlobeLatLon,
  setViewerProjection,
  zoomViewerByFactor,
} from "./components/cesium_helpers.js";
import { getPaletteLut, normalizeLon180 } from "./components/color_scale.js";
import { initStarfield } from "./components/starfield.js";
import { PALETTES } from "./state.js";
import { escapeHtml, setButtonPressed, setSpinButtonState } from "./ui/dom.js";

const PLANETARY_TILES = {
  moon: {
    bgColor: "#141821",
    fallbackRamp: [[34, 40, 50], [168, 176, 190]],
    radiusEquatorial: 1737400,
    radiusPolar: 1737400,
    defaultBasemap: "wac_hybrid",
    basemaps: {
      lola_shade: {
        label: "Basemap: LOLA Shaded Relief",
        layers: [
          {
            url: "https://trek.nasa.gov/tiles/Moon/EQ/LRO_LOLA_Shade_Global_128ppd_v04/1.0.0/default/default028mm/{TileMatrix}/{TileRow}/{TileCol}.png",
            layer: "LRO_LOLA_Shade_Global_128ppd_v04",
            format: "image/png",
            tileMatrixLabels: ["0", "1", "2", "3", "4", "5"],
            maximumLevel: 5,
            attribution: "NASA Moon Trek / LRO LOLA Shaded Relief (128 ppd)",
            alpha: 1.0,
          },
        ],
      },
      lola_clr: {
        label: "Basemap: LOLA Color Elevation",
        layers: [
          {
            url: "https://trek.nasa.gov/tiles/Moon/EQ/LRO_LOLA_ClrShade_Global_128ppd_v04/1.0.0/default/default028mm/{TileMatrix}/{TileRow}/{TileCol}.png",
            layer: "LRO_LOLA_ClrShade_Global_128ppd_v04",
            format: "image/png",
            tileMatrixLabels: ["0", "1", "2", "3", "4", "5"],
            maximumLevel: 5,
            attribution: "NASA Moon Trek / LRO LOLA Color Shaded (128 ppd)",
            alpha: 1.0,
          },
        ],
      },
      wac_hybrid: {
        label: "Basemap: LRO WAC + LOLA Polar Fill",
        layers: [
          {
            url: "https://trek.nasa.gov/tiles/Moon/EQ/LRO_LOLA_Shade_Global_128ppd_v04/1.0.0/default/default028mm/{TileMatrix}/{TileRow}/{TileCol}.png",
            layer: "LRO_LOLA_Shade_Global_128ppd_v04",
            format: "image/png",
            tileMatrixLabels: ["0", "1", "2", "3", "4", "5"],
            maximumLevel: 5,
            attribution: "NASA Moon Trek / LOLA",
            alpha: 1.0,
          },
          {
            url: "https://trek.nasa.gov/tiles/Moon/EQ/LRO_WAC_Mosaic_Global_303ppd_v02/1.0.0/default/default028mm/{TileMatrix}/{TileRow}/{TileCol}.jpg",
            layer: "LRO_WAC_Mosaic_Global_303ppd_v02",
            format: "image/jpeg",
            tileMatrixLabels: ["0", "1", "2", "3", "4", "5", "6", "7", "8"],
            maximumLevel: 8,
            attribution: "NASA Moon Trek / LRO WAC (303 ppd) + LOLA",
            alpha: 0.72,
          },
        ],
      },
    },
  },
  mars: {
    bgColor: "#26120c",
    fallbackRamp: [[62, 26, 18], [212, 134, 96]],
    radiusEquatorial: 3396190,
    radiusPolar: 3376200,
    defaultBasemap: "viking",
    basemaps: {
      viking: {
        label: "Basemap: Viking MDIM2.1 Color",
        layers: [
          {
            url: "https://trek.nasa.gov/tiles/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/default/default028mm/{TileMatrix}/{TileRow}/{TileCol}.jpg",
            layer: "Mars_Viking_MDIM21_ClrMosaic_global_232m",
            format: "image/jpeg",
            tileMatrixLabels: ["0", "1", "2", "3", "4", "5", "6", "7"],
            maximumLevel: 7,
            attribution: "NASA Mars Trek / Viking MDIM2.1 (232 m)",
            alpha: 1.0,
          },
        ],
      },
    },
  },
};

const plState = {
  metadata: null,
  body: "moon",
  basemapByBody: {
    moon: PLANETARY_TILES.moon.defaultBasemap,
    mars: PLANETARY_TILES.mars.defaultBasemap,
  },
  presetId: null,
  target: null,
  overlayParam: "none",
  palette: "bioluminescent",
  isGlobe: true,
  autoSpin: true,
  userInteracting: false,
  pointerDown: false,
  map: null,
  mapReady: false,
  gridCache: {},
  shadedUrlCache: {},
  activeSlice: null,
};

let _viewer = null;
let _viewerBody = null;
let _interaction = null;
let _fallbackLayer = null;
let _basemapLayers = [];
let _overlayLayer = null;
let _pinBillboards = null;
let _pinLabels = null;
let _selectedRing = null;
let _pinImages = null;
const _layerTokens = { fallback: 0, overlay: 0 };

function getPlanetaryPinImages() {
  if (_pinImages) return _pinImages;
  _pinImages = {
    pinDefault: makePinDataUrl({ fill: "#e2e8f0", stroke: "#09101d", radius: 5.5, strokeWidth: 1.8, glow: false }),
    pinSelected: makePinDataUrl({ fill: "#fbbf24", stroke: "#09101d", radius: 8, strokeWidth: 2, glow: true }),
    selectedRing: makePinDataUrl({ fill: "#38bdf8", stroke: "#38bdf8", radius: 13, strokeWidth: 2.4, glow: false }),
  };
  return _pinImages;
}

function getBodyEllipsoid(body) {
  const Cesium = window.Cesium;
  const spec = PLANETARY_TILES[body] || PLANETARY_TILES.moon;
  return new Cesium.Ellipsoid(spec.radiusEquatorial, spec.radiusEquatorial, spec.radiusPolar);
}

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

function makeTwoStopLut(rgbStart, rgbEnd) {
  const lut = new Uint8Array(256 * 3);
  for (let i = 0; i < 256; i++) {
    const t = i / 255;
    lut[i * 3] = Math.round(rgbStart[0] + t * (rgbEnd[0] - rgbStart[0]));
    lut[i * 3 + 1] = Math.round(rgbStart[1] + t * (rgbEnd[1] - rgbStart[1]));
    lut[i * 3 + 2] = Math.round(rgbStart[2] + t * (rgbEnd[2] - rgbStart[2]));
  }
  return lut;
}

// Collapse multi-valued pole rows into a uniform azimuthal mean so spherical rendering never forms radial starburst spokes
function buildPoleNormalizedRows(values) {
  const nLat = values.length;
  if (nLat < 2) return values;
  const rows = values.slice();
  const rowMean = (row) => {
    let sum = 0;
    for (let j = 0; j < row.length; j++) sum += row[j];
    return sum / Math.max(1, row.length);
  };
  const zeroFraction = (row) => {
    let zeros = 0;
    for (let j = 0; j < row.length; j++) {
      if (row[j] === 0) zeros++;
    }
    return zeros / Math.max(1, row.length);
  };

  const collapsePoleRow = (row, adjacentRow) => {
    const adjMean = rowMean(adjacentRow);
    // Some global grids zero-pad exact ±90° pole rows; fall back to the adjacent ring mean when valid
    const fillVal = zeroFraction(row) >= 0.8 && Math.abs(adjMean) > 1e-6 ? adjMean : rowMean(row);
    return new Array(row.length).fill(fillVal);
  };

  rows[0] = collapsePoleRow(values[0], values[1]);
  rows[nLat - 1] = collapsePoleRow(values[nLat - 1], values[nLat - 2]);
  return rows;
}

// Direct equirectangular -90..+90 projection (Cesium SingleTileImageryProvider wraps directly without Mercator warp)
function renderSliceToEquirectangularDataUrl(slice, paletteNameOrLut, alpha = 225) {
  const w = 720;
  const h = 360;
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  const img = ctx.createImageData(w, h);
  const data = img.data;

  const step = Number(slice.step_deg);
  const nLat = slice.lats.length;
  const nLon = slice.lons.length;
  const values = buildPoleNormalizedRows(slice.values);

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
  const lut = paletteNameOrLut instanceof Uint8Array ? paletteNameOrLut : getPaletteLut(paletteNameOrLut);

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
    const lat = 90.0 - (180.0 * (py + 0.5)) / h;
    const yf = (lat + 90.0) / step;
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

function populateBasemapDropdown(body) {
  const sel = document.getElementById("pl-basemap-select");
  if (!sel) return;
  const spec = PLANETARY_TILES[body] || PLANETARY_TILES.moon;
  const basemaps = spec.basemaps || {};
  const entries = Object.entries(basemaps);
  sel.innerHTML = "";
  for (const [id, cfg] of entries) {
    const opt = document.createElement("option");
    opt.value = id;
    opt.textContent = cfg.label;
    sel.appendChild(opt);
  }
  const activeId = basemaps[plState.basemapByBody[body]] ? plState.basemapByBody[body] : spec.defaultBasemap;
  plState.basemapByBody[body] = activeId;
  sel.value = activeId;
  sel.disabled = entries.length <= 1;
}

function applyBasemapLayers(body) {
  if (!_viewer || _viewer.isDestroyed()) return;
  const Cesium = window.Cesium;
  const spec = PLANETARY_TILES[body] || PLANETARY_TILES.moon;
  const ellipsoid = _viewer.scene.globe.ellipsoid;
  const basemapId = plState.basemapByBody[body] || spec.defaultBasemap;
  const basemapCfg = spec.basemaps?.[basemapId] || Object.values(spec.basemaps || {})[0];

  for (const layer of _basemapLayers) {
    if (_viewer.imageryLayers.contains(layer)) {
      _viewer.imageryLayers.remove(layer, true);
    }
  }
  _basemapLayers = [];
  if (!basemapCfg?.layers?.length) return;

  // Insert Trek imagery layers directly after fallback layer (index 1+) and beneath overlay layer
  let insertIdx = _fallbackLayer ? _viewer.imageryLayers.indexOf(_fallbackLayer) + 1 : 0;
  if (insertIdx < 0) insertIdx = 0;

  for (const layerSpec of basemapCfg.layers) {
    const provider = new Cesium.WebMapTileServiceImageryProvider({
      url: layerSpec.url,
      layer: layerSpec.layer,
      style: "default",
      format: layerSpec.format || "image/png",
      tileMatrixSetID: "default028mm",
      tileMatrixLabels: layerSpec.tileMatrixLabels,
      tilingScheme: new Cesium.GeographicTilingScheme({ ellipsoid }),
      tileWidth: 256,
      tileHeight: 256,
      maximumLevel: layerSpec.maximumLevel,
      credit: new Cesium.Credit(layerSpec.attribution),
    });
    const imgLayer = _viewer.imageryLayers.addImageryProvider(provider, insertIdx++);
    imgLayer.alpha = layerSpec.alpha ?? 1.0;
    _basemapLayers.push(imgLayer);
  }
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

async function replaceSingleTileLayer(slotKey, getLayer, setLayer, dataUrl, { alpha = 1.0, show = true } = {}) {
  if (!_viewer || _viewer.isDestroyed()) return null;
  const token = ++_layerTokens[slotKey];
  const viewerAtCall = _viewer;
  const Cesium = window.Cesium;
  const ellipsoid = viewerAtCall.scene.globe.ellipsoid;
  const provider = await Cesium.SingleTileImageryProvider.fromUrl(dataUrl, {
    rectangle: Cesium.Rectangle.fromDegrees(-180, -90, 180, 90, new Cesium.Rectangle()),
    ellipsoid,
  });
  if (token !== _layerTokens[slotKey] || _viewer !== viewerAtCall || viewerAtCall.isDestroyed()) {
    return null;
  }
  const currentLayer = getLayer();
  const insertIdx = currentLayer ? viewerAtCall.imageryLayers.indexOf(currentLayer) : -1;
  if (currentLayer && insertIdx >= 0) {
    viewerAtCall.imageryLayers.remove(currentLayer, true);
  }
  const nextLayer =
    insertIdx >= 0
      ? viewerAtCall.imageryLayers.addImageryProvider(provider, insertIdx)
      : viewerAtCall.imageryLayers.addImageryProvider(provider);
  nextLayer.alpha = alpha;
  nextLayer.show = show;
  setLayer(nextLayer);
  return nextLayer;
}

async function refreshOverlayLayer() {
  if (!_viewer || _viewer.isDestroyed() || !plState.mapReady) return;

  if (plState.overlayParam === "none") {
    _layerTokens.overlay++;
    plState.activeSlice = null;
    if (_overlayLayer) _overlayLayer.show = false;
    updateLegendUI(null, 0, 0);
    return;
  }

  try {
    const bodyAtFetch = plState.body;
    const paramAtFetch = plState.overlayParam;
    const slice = await fetchPlanetaryGridSlice(bodyAtFetch, paramAtFetch);
    if (plState.body !== bodyAtFetch || plState.overlayParam !== paramAtFetch) return;
    plState.activeSlice = slice;
    const { url, minV, maxV } = renderSliceToEquirectangularDataUrl(slice, plState.palette, 230);
    const placed = await replaceSingleTileLayer(
      "overlay",
      () => _overlayLayer,
      (layer) => {
        _overlayLayer = layer;
      },
      url,
      { alpha: 0.68, show: true },
    );
    if (!placed) return;
    const paramSpec = plState.metadata.parameters.find((p) => p.id === paramAtFetch);
    updateLegendUI(paramSpec, minV, maxV);
  } catch (err) {
    console.warn("Planetary overlay fetch failed:", err);
  }
}

async function refreshFallbackShadedTerrain() {
  if (!_viewer || _viewer.isDestroyed() || !plState.mapReady) return;
  const body = plState.body;
  try {
    let url = plState.shadedUrlCache[body];
    if (!url) {
      const slice = await fetchPlanetaryGridSlice(body, "elevation_m");
      const ramp = (PLANETARY_TILES[body] || PLANETARY_TILES.moon).fallbackRamp;
      const fallbackLut = makeTwoStopLut(ramp[0], ramp[1]);
      url = renderSliceToEquirectangularDataUrl(slice, fallbackLut, 255).url;
      plState.shadedUrlCache[body] = url;
    }
    if (plState.body === body) {
      await replaceSingleTileLayer(
        "fallback",
        () => _fallbackLayer,
        (layer) => {
          _fallbackLayer = layer;
        },
        url,
        { alpha: 0.94, show: true },
      );
    }
  } catch {
    // Keep solid fallback if API unavailable
  }
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

  if (_viewer && !_viewer.isDestroyed() && _pinBillboards && _pinLabels) {
    const Cesium = window.Cesium;
    const ellipsoid = _viewer.scene.globe.ellipsoid;
    const imgs = getPlanetaryPinImages();
    const pinHeight = ellipsoid.maximumRadius * 0.0025;

    _pinBillboards.removeAll();
    _pinLabels.removeAll();
    for (const p of presets) {
      const isSelected = p.id === plState.presetId;
      const lon = normalizeLon180(p.lon);
      const pos = Cesium.Cartesian3.fromDegrees(lon, p.lat, pinHeight, ellipsoid);
      _pinBillboards.add({
        id: { kind: "mission_pin", id: p.id, name: p.name },
        position: pos,
        image: isSelected ? imgs.pinSelected : imgs.pinDefault,
      });
      _pinLabels.add({
        id: { kind: "mission_pin", id: p.id, name: p.name },
        position: pos,
        text: p.name,
        font: "600 11px system-ui, -apple-system, sans-serif",
        fillColor: Cesium.Color.fromCssColorString(isSelected ? "#fde68a" : "#e2e8f0"),
        outlineColor: Cesium.Color.fromCssColorString("#060b16"),
        outlineWidth: 3,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        verticalOrigin: Cesium.VerticalOrigin.TOP,
        pixelOffset: new Cesium.Cartesian2(0, 11),
      });
    }

    if (_selectedRing) {
      if (plState.target) {
        const lon = normalizeLon180(plState.target.lon);
        _selectedRing.position = Cesium.Cartesian3.fromDegrees(lon, plState.target.lat, pinHeight * 1.15, ellipsoid);
        _selectedRing.show = true;
      } else {
        _selectedRing.show = false;
      }
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
  const bodyChanged = plState.body !== target.body;
  plState.body = target.body;
  plState.presetId = presetId;
  plState.target = target;
  setButtonPressed(document.getElementById("pl-btn-moon"), target.body === "moon");
  setButtonPressed(document.getElementById("pl-btn-mars"), target.body === "mars");
  if (bodyChanged || _viewerBody !== target.body) {
    await mountPlanetaryViewer(target.body);
  }
  updateMarkersAndList();
  renderTargetDetails();
  await refreshOverlayLayer();
  if (fly && _viewer && !_viewer.isDestroyed()) {
    plState.userInteracting = true;
    flyToLatLon(_viewer, {
      lon: normalizeLon180(target.lon),
      lat: target.lat,
      zoom: 2.6,
      durationSec: 1.2,
    });
    setTimeout(() => {
      if (!plState.pointerDown) plState.userInteracting = false;
    }, 1400);
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
  if (fly && _viewer && !_viewer.isDestroyed()) {
    plState.userInteracting = true;
    flyToLatLon(_viewer, {
      lon: lon180,
      lat: clampedLat,
      zoom: 2.4,
      durationSec: 1.1,
    });
    setTimeout(() => {
      if (!plState.pointerDown) plState.userInteracting = false;
    }, 1300);
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
    mountPlanetaryViewer(nextBody).then(() => refreshOverlayLayer());
  }
}

const _plSpinController = createAutoSpinController({
  getViewer: () => _viewer,
  shouldSpin: () =>
    Boolean(
      !document.hidden &&
        _viewer &&
        !_viewer.isDestroyed() &&
        plState.mapReady &&
        plState.isGlobe &&
        plState.autoSpin &&
        !plState.userInteracting &&
        !plState.pointerDown &&
        cameraHeightToApproxZoom(_viewer) < 2.2,
    ),
  rateDegPerSec: 2.0,
});

async function mountPlanetaryViewer(body) {
  const Cesium = window.Cesium;
  if (_interaction) {
    _interaction.destroy();
    _interaction = null;
  }
  if (_viewer && !_viewer.isDestroyed()) {
    _viewer.destroy();
  }
  _viewer = null;
  _fallbackLayer = null;
  _basemapLayers = [];
  _overlayLayer = null;
  _pinBillboards = null;
  _pinLabels = null;
  _selectedRing = null;
  plState.mapReady = false;
  _viewerBody = body;

  const spec = PLANETARY_TILES[body] || PLANETARY_TILES.moon;
  const ellipsoid = getBodyEllipsoid(body);
  populateBasemapDropdown(body);

  const viewer = createCesiumViewer("planetary-map", {
    ellipsoid,
    showAtmosphere: false,
    baseColor: spec.bgColor,
    initialLon: plState.target ? normalizeLon180(plState.target.lon) : 23,
    initialLat: plState.target ? plState.target.lat : 0,
    initialZoom: 1.65,
  });
  _viewer = viewer;
  plState.map = viewer;

  // Layer 0: Full -90..+90 equirectangular NASA LOLA/MOLA elevation relief (offline/loading fallback)
  const solidUrl = makeSolidFallbackDataUrl(body);
  const fallbackProvider = await Cesium.SingleTileImageryProvider.fromUrl(solidUrl, {
    rectangle: Cesium.Rectangle.fromDegrees(-180, -90, 180, 90, new Cesium.Rectangle()),
    ellipsoid,
  });
  if (_viewer !== viewer || viewer.isDestroyed()) return;
  _fallbackLayer = viewer.imageryLayers.addImageryProvider(fallbackProvider);
  _fallbackLayer.alpha = 0.94;

  // Layer 1+: NASA Solar System Treks EPSG:4326 WMTS basemap (Moon defaults to LRO WAC + LOLA Polar Fill)
  applyBasemapLayers(body);

  // Top Layer: Parameter overlay layer (equirectangular -90..+90)
  _overlayLayer = viewer.imageryLayers.addImageryProvider(fallbackProvider);
  _overlayLayer.alpha = 0.68;
  _overlayLayer.show = false;

  _pinBillboards = viewer.scene.primitives.add(new Cesium.BillboardCollection({ scene: viewer.scene }));
  _pinLabels = viewer.scene.primitives.add(new Cesium.LabelCollection({ scene: viewer.scene }));
  const ringColl = viewer.scene.primitives.add(new Cesium.BillboardCollection({ scene: viewer.scene }));
  _selectedRing = ringColl.add({
    image: getPlanetaryPinImages().selectedRing,
    position: Cesium.Cartesian3.fromDegrees(0, 0, ellipsoid.maximumRadius * 0.003, ellipsoid),
    show: false,
    width: 26,
    height: 26,
  });

  const cursorPillEl = document.getElementById("pl-cursor-pill");
  const renderCursorPill = (pos) => {
    if (!cursorPillEl) return;
    const coords = pickGlobeLatLon(viewer, pos);
    if (!coords) return;
    const lat = coords.lat;
    const lon = normalizeLon180(coords.lon);
    let extra = "";
    if (plState.activeSlice) {
      const val = bilinearSampleSlice(plState.activeSlice, lat, lon);
      extra = ` · ${plState.overlayParam}: ${val.toFixed(1)}`;
    }
    cursorPillEl.textContent = `${plState.body.toUpperCase()} · ${lat.toFixed(2)}°, ${lon.toFixed(2)}°${extra}`;
  };

  _interaction = bindCesiumCameraInteraction(viewer, {
    onPointerDown: () => {
      plState.pointerDown = true;
      plState.userInteracting = true;
    },
    onPointerUp: () => {
      plState.pointerDown = false;
      plState.userInteracting = false;
      _plSpinController.requestFrame();
    },
    onWheelStart: () => {
      plState.userInteracting = true;
    },
    onWheelIdle: () => {
      plState.userInteracting = false;
      _plSpinController.requestFrame();
    },
    onHoverFrame: renderCursorPill,
    onClick: (pos) => {
      const picked = viewer.scene.pick(pos);
      if (picked?.id?.kind === "mission_pin") {
        selectPreset(picked.id.id, true);
        return;
      }
      const coords = pickGlobeLatLon(viewer, pos);
      if (coords) {
        extractCustomCoord(coords.lat, coords.lon, false);
      }
    },
    wheelIdleMs: 2000,
  });

  viewer.camera.changed.addEventListener(() => _plSpinController.requestFrame());

  setViewerProjection(viewer, plState.isGlobe);
  plState.mapReady = true;
  updateMarkersAndList();
  refreshFallbackShadedTerrain();
  refreshOverlayLayer();
  _plSpinController.start();
}

function bindEvents() {
  document.getElementById("pl-btn-moon").addEventListener("click", () => switchBody("moon"));
  document.getElementById("pl-btn-mars").addEventListener("click", () => switchBody("mars"));

  document.getElementById("pl-basemap-select")?.addEventListener("change", (e) => {
    plState.basemapByBody[plState.body] = e.target.value;
    applyBasemapLayers(plState.body);
  });

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
    _plSpinController.requestFrame();
  });

  document.getElementById("pl-btn-proj").addEventListener("click", (e) => {
    plState.isGlobe = !plState.isGlobe;
    setViewerProjection(_viewer, plState.isGlobe);
    e.target.textContent = plState.isGlobe ? "3D Globe: ON" : "2D Map: ON";
    e.target.setAttribute("aria-pressed", plState.isGlobe ? "true" : "false");
    _plSpinController.requestFrame();
  });

  document.getElementById("pl-zoom-in")?.addEventListener("click", () => {
    zoomViewerByFactor(_viewer, 1.55);
    _plSpinController.requestFrame();
  });
  document.getElementById("pl-zoom-out")?.addEventListener("click", () => {
    zoomViewerByFactor(_viewer, 1 / 1.55);
    _plSpinController.requestFrame();
  });
  document.getElementById("pl-zoom-reset")?.addEventListener("click", () => {
    flyToLatLon(_viewer, {
      lon: plState.target ? normalizeLon180(plState.target.lon) : 23,
      lat: plState.target ? plState.target.lat : 0,
      zoom: 1.65,
      durationSec: 0.7,
    });
    _plSpinController.requestFrame();
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

  await mountPlanetaryViewer(plState.body);

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
