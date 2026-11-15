// 3D Earth Globe (CesiumJS), EPSG:4326 NASA GIBS basemaps, batched H3 WebGL primitives & ranked pins

import { fetchRawParameter } from "../api.js";
import { PALETTES, state } from "../state.js";
import { escapeHtml, setSpinButtonState } from "../ui/dom.js";
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
} from "./cesium_helpers.js";
import {
  computeLayerColorRange,
  getPaletteLut,
  normalizeLon180,
  updateLegendGradient,
  updateLegendLabels,
  writeCellRgbaBytes,
} from "./color_scale.js";

export { updateLegendGradient };

const H3_CHUNK_SIZE = 4500;
const H3_FILL_HEIGHT_M = 600;
const H3_OUTLINE_HEIGHT_M = 950;
const PIN_HEIGHT_M = 4000;

function shortPinTitle(name) {
  if (!name) return "";
  return name.length > 26 ? `${name.slice(0, 24)}…` : name;
}

let _cachedGeojsonRef = null;
let _siteCoordsById = new Map();
let _sitePropsById = new Map();
let _siteRingsById = new Map();
let _displayDataVersion = 0;
let _lastColorRange = { minVal: 0, maxVal: 100 };

// Cesium scene objects
let _viewer = null;
let _blueMarbleLayer = null;
let _modisLayer = null;
let _h3FillBatches = []; // Array<{ prim: Cesium.Primitive, instIds: string[] }>
let _h3OutlineBatches = [];
let _h3OutlinesRequested = false;
let _h3OutlinesVisible = false;
let _cellInstById = new Map(); // cellId -> Array<{ prim, instId }>
let _rgbaById = new Map(); // cellId -> Uint8Array(4)
let _dirtyColorSync = false;
let _h3BuildToken = 0;

let _topH3Billboards = null;
let _topH3Labels = null;
let _hotspotBillboards = null;
let _hotspotLabels = null;
let _selectedPrimitives = null;
let _selectedOutlinePrim = null;
let _beaconBillboard = null;
let _pinImages = null;

function getPinImages() {
  if (_pinImages) return _pinImages;
  _pinImages = {
    top3H3: makePinDataUrl({ fill: "#2dd4bf", stroke: "#ffffff", radius: 8, strokeWidth: 2, glow: true }),
    topKH3: makePinDataUrl({ fill: "#0d9488", stroke: "#ffffff", radius: 6, strokeWidth: 1.8, glow: false }),
    hsWellKnown: makePinDataUrl({ fill: "#f59e0b", stroke: "#ffffff", radius: 6.5, strokeWidth: 1.8, glow: true }),
    hsNovel: makePinDataUrl({ fill: "#38bdf8", stroke: "#ffffff", radius: 6.5, strokeWidth: 1.8, glow: true }),
    beacon: makePinDataUrl({ fill: "#2dd4bf", stroke: "#fde047", radius: 13, strokeWidth: 2.6, glow: false }),
  };
  return _pinImages;
}

function extractFeatureRings(geom) {
  if (!geom?.coordinates) return [];
  if (geom.type === "Polygon") {
    return geom.coordinates[0]?.length >= 3 ? [geom.coordinates[0]] : [];
  }
  if (geom.type === "MultiPolygon") {
    const out = [];
    for (const poly of geom.coordinates) {
      if (poly?.[0]?.length >= 3) out.push(poly[0]);
    }
    return out;
  }
  return [];
}

function ensureGeojsonIndexes() {
  if (_cachedGeojsonRef !== state.earthGeojson) {
    _cachedGeojsonRef = state.earthGeojson;
    _siteCoordsById = new Map();
    _sitePropsById = new Map();
    _siteRingsById = new Map();
    for (const f of state.earthGeojson?.features || []) {
      const id = f?.properties?.id;
      if (!id) continue;
      _sitePropsById.set(id, f.properties);
      const rings = extractFeatureRings(f.geometry);
      if (!rings.length) continue;
      _siteRingsById.set(id, rings);

      let resolved = false;
      if (typeof window !== "undefined" && window.h3?.cellToLatLng) {
        try {
          const [cLat, cLon] = window.h3.cellToLatLng(id);
          if (Number.isFinite(cLat) && Number.isFinite(cLon)) {
            _siteCoordsById.set(id, [cLon, cLat]);
            resolved = true;
          }
        } catch {
          // Fall through to ring averaging for non-H3 IDs
        }
      }
      if (!resolved) {
        let sx = 0;
        let sy = 0;
        let cnt = 0;
        for (const ring of rings) {
          for (const pt of ring) {
            sx += pt[0];
            sy += pt[1];
            cnt += 1;
          }
        }
        if (cnt > 0) {
          _siteCoordsById.set(id, [sx / cnt, sy / cnt]);
        }
      }
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

function ringToCartesianArray(ring) {
  const Cesium = window.Cesium;
  const flat = new Array(ring.length * 2);
  for (let i = 0; i < ring.length; i++) {
    flat[i * 2] = ring[i][0];
    flat[i * 2 + 1] = ring[i][1];
  }
  return Cesium.Cartesian3.fromDegreesArray(flat);
}

function buildOuterPerimeterPolylineInstances(rings, heightM, colorAttr, width, idPrefix) {
  const Cesium = window.Cesium;
  const instances = [];
  let segIdx = 0;
  for (const ring of rings) {
    for (let i = 0; i < ring.length - 1; i++) {
      const a = ring[i];
      const b = ring[i + 1];
      // Omit artificial polar-wedge spoke edges and ±180° antimeridian clip seams
      if (Math.abs(a[1]) >= 89.999 || Math.abs(b[1]) >= 89.999) continue;
      if (Math.abs(Math.abs(a[0]) - 180.0) < 1e-3 && Math.abs(Math.abs(b[0]) - 180.0) < 1e-3) continue;
      instances.push(
        new Cesium.GeometryInstance({
          id: `${idPrefix}:edge:${segIdx++}`,
          geometry: new Cesium.PolylineGeometry({
            positions: Cesium.Cartesian3.fromDegreesArrayHeights([a[0], a[1], heightM, b[0], b[1], heightM]),
            width,
            vertexFormat: Cesium.PolylineColorAppearance.VERTEX_FORMAT,
          }),
          attributes: { color: colorAttr },
        }),
      );
    }
  }
  return instances;
}

export function highlightSelectedSiteOnMap(siteId, explicitCoords = null) {
  if (!_viewer || _viewer.isDestroyed()) return;
  const Cesium = window.Cesium;
  const targetId = siteId || "";

  if (_selectedOutlinePrim && _selectedPrimitives) {
    _selectedPrimitives.remove(_selectedOutlinePrim);
    _selectedOutlinePrim = null;
  }

  ensureGeojsonIndexes();
  const rings = targetId ? _siteRingsById.get(targetId) : null;
  if (rings?.length && _selectedPrimitives) {
    const selColor = Cesium.ColorGeometryInstanceAttribute.fromColor(
      Cesium.Color.fromCssColorString("#38bdf8").withAlpha(0.98),
    );
    if (rings.length === 1) {
      const instances = [
        new Cesium.GeometryInstance({
          id: `sel:${targetId}:0`,
          geometry: new Cesium.PolygonOutlineGeometry({
            polygonHierarchy: new Cesium.PolygonHierarchy(ringToCartesianArray(rings[0])),
            height: 1500,
          }),
          attributes: { color: selColor },
        }),
      ];
      _selectedOutlinePrim = _selectedPrimitives.add(
        new Cesium.Primitive({
          geometryInstances: instances,
          appearance: new Cesium.PerInstanceColorAppearance({ flat: true, translucent: true }),
          asynchronous: false,
        }),
      );
    } else {
      const polyInstances = buildOuterPerimeterPolylineInstances(rings, 1500, selColor, 2.0, `sel:${targetId}`);
      if (polyInstances.length) {
        _selectedOutlinePrim = _selectedPrimitives.add(
          new Cesium.Primitive({
            geometryInstances: polyInstances,
            appearance: new Cesium.PolylineColorAppearance({ translucent: true }),
            asynchronous: false,
          }),
        );
      }
    }
  }

  if (_beaconBillboard) {
    const coords = targetId ? resolveSiteCoords(targetId, explicitCoords) : null;
    if (coords) {
      _beaconBillboard.position = Cesium.Cartesian3.fromDegrees(coords[0], coords[1], PIN_HEIGHT_M + 1000);
      _beaconBillboard.show = true;
    } else {
      _beaconBillboard.show = false;
    }
  }
}

export function flyToSiteOnGlobe(lon, lat, zoom = 3.4, pauseSpin = true) {
  if (!_viewer || _viewer.isDestroyed()) return;
  if (pauseSpin && state.autoSpin) {
    state.autoSpin = false;
    setSpinButtonState(document.getElementById("btn-toggle-spin"), false);
  }
  state.userInteracting = true;
  clearTimeout(state.flyToTimer);
  flyToLatLon(_viewer, { lon, lat, zoom, durationSec: 1.25 });
  state.flyToTimer = setTimeout(() => {
    if (!state.pointerDown) state.userInteracting = false;
  }, 1400);
}

export function setEarthProjection(isGlobe) {
  state.isGlobe = Boolean(isGlobe);
  setViewerProjection(_viewer, state.isGlobe);
  syncOutlineVisibilityFromZoom();
  requestAutoSpinFrame();
}

export function zoomEarthGlobe(factor = 1.55) {
  if (!_viewer || _viewer.isDestroyed()) return;
  clearTimeout(state.flyToTimer);
  zoomViewerByFactor(_viewer, factor);
  syncOutlineVisibilityFromZoom();
  requestAutoSpinFrame();
}

export function resetEarthGlobeView() {
  if (!_viewer || _viewer.isDestroyed()) return;
  flyToSiteOnGlobe(-20, 28, 1.55, false);
}

function flushPendingColorsToPrimitives() {
  if (!_dirtyColorSync || !_h3FillBatches.length) return;
  let anyNotReady = false;
  for (const batch of _h3FillBatches) {
    if (!batch.prim.ready) {
      anyNotReady = true;
      continue;
    }
    for (const [cellId, instId] of batch.cellEntries) {
      const rgba = _rgbaById.get(cellId);
      if (!rgba) continue;
      const attrs = batch.prim.getGeometryInstanceAttributes(instId);
      if (attrs) {
        attrs.color = rgba;
      }
    }
  }
  _dirtyColorSync = anyNotReady;
}

function buildChunkInstances(features, startIdx, endIdx, isOutline) {
  const Cesium = window.Cesium;
  const instances = [];
  const polylineInstances = [];
  const cellEntries = [];
  const defaultRgba = new Uint8Array([15, 23, 42, 0]);
  const outlineAttr = isOutline
    ? Cesium.ColorGeometryInstanceAttribute.fromColor(
        Cesium.Color.fromCssColorString("rgba(226, 232, 240, 0.32)"),
      )
    : null;

  for (let i = startIdx; i < endIdx; i++) {
    const feat = features[i];
    const cellId = feat?.properties?.id;
    if (!cellId) continue;
    const rings = extractFeatureRings(feat.geometry);
    if (!rings.length) continue;

    if (isOutline && rings.length > 1) {
      polylineInstances.push(
        ...buildOuterPerimeterPolylineInstances(rings, H3_OUTLINE_HEIGHT_M, outlineAttr, 1.0, cellId),
      );
      continue;
    }

    const rgba = !isOutline ? _rgbaById.get(cellId) || defaultRgba : null;
    for (let rIdx = 0; rIdx < rings.length; rIdx++) {
      const positions = ringToCartesianArray(rings[rIdx]);
      const instId = rIdx === 0 ? cellId : `${cellId}#${rIdx}`;
      const geom = isOutline
        ? new Cesium.PolygonOutlineGeometry({
            polygonHierarchy: new Cesium.PolygonHierarchy(positions),
            height: H3_OUTLINE_HEIGHT_M,
          })
        : new Cesium.PolygonGeometry({
            polygonHierarchy: new Cesium.PolygonHierarchy(positions),
            height: H3_FILL_HEIGHT_M,
            vertexFormat: Cesium.PerInstanceColorAppearance.VERTEX_FORMAT,
          });
      instances.push(
        new Cesium.GeometryInstance({
          id: instId,
          geometry: geom,
          attributes: {
            color: isOutline
              ? outlineAttr
              : new Cesium.ColorGeometryInstanceAttribute(rgba[0], rgba[1], rgba[2], rgba[3]),
          },
        }),
      );
      if (!isOutline) {
        cellEntries.push([cellId, instId]);
      }
    }
  }
  return { instances, polylineInstances, cellEntries };
}

function startBuildingH3FillPrimitives() {
  if (!_viewer || _viewer.isDestroyed() || !state.earthGeojson?.features?.length) return;
  const Cesium = window.Cesium;
  const token = ++_h3BuildToken;
  const features = state.earthGeojson.features;

  for (const b of _h3FillBatches) {
    _viewer.scene.primitives.remove(b.prim);
  }
  _h3FillBatches = [];
  _cellInstById = new Map();

  let offset = 0;
  function processNextChunk() {
    if (token !== _h3BuildToken || !_viewer || _viewer.isDestroyed()) return;
    const end = Math.min(features.length, offset + H3_CHUNK_SIZE);
    const { instances, cellEntries } = buildChunkInstances(features, offset, end, false);
    if (instances.length) {
      const prim = _viewer.scene.primitives.add(
        new Cesium.Primitive({
          geometryInstances: instances,
          appearance: new Cesium.PerInstanceColorAppearance({
            flat: true,
            translucent: true,
          }),
          asynchronous: false,
        }),
      );
      const batch = { prim, cellEntries };
      _h3FillBatches.push(batch);
      for (const [cellId, instId] of cellEntries) {
        let arr = _cellInstById.get(cellId);
        if (!arr) {
          arr = [];
          _cellInstById.set(cellId, arr);
        }
        arr.push({ prim, instId });
      }
      _dirtyColorSync = true;
    }
    offset = end;
    if (offset < features.length) {
      setTimeout(processNextChunk, 0);
    } else {
      _dirtyColorSync = true;
    }
  }

  processNextChunk();
}

function ensureH3OutlinePrimitives() {
  if (_h3OutlinesRequested || !_viewer || _viewer.isDestroyed() || !state.earthGeojson?.features?.length) {
    return;
  }
  _h3OutlinesRequested = true;
  const Cesium = window.Cesium;
  const features = state.earthGeojson.features;
  const token = _h3BuildToken;
  let offset = 0;

  function processNextOutlineChunk() {
    if (token !== _h3BuildToken || !_viewer || _viewer.isDestroyed()) return;
    const end = Math.min(features.length, offset + H3_CHUNK_SIZE);
    const { instances, polylineInstances } = buildChunkInstances(features, offset, end, true);
    if (instances.length) {
      const prim = _viewer.scene.primitives.add(
        new Cesium.Primitive({
          geometryInstances: instances,
          appearance: new Cesium.PerInstanceColorAppearance({
            flat: true,
            translucent: true,
          }),
          asynchronous: false,
          show: _h3OutlinesVisible,
        }),
      );
      _h3OutlineBatches.push(prim);
    }
    if (polylineInstances.length) {
      const polyPrim = _viewer.scene.primitives.add(
        new Cesium.Primitive({
          geometryInstances: polylineInstances,
          appearance: new Cesium.PolylineColorAppearance({ translucent: true }),
          asynchronous: false,
          show: _h3OutlinesVisible,
        }),
      );
      _h3OutlineBatches.push(polyPrim);
    }
    offset = end;
    if (offset < features.length) {
      setTimeout(processNextOutlineChunk, 0);
    }
  }

  processNextOutlineChunk();
}

function syncOutlineVisibilityFromZoom() {
  if (!_viewer || _viewer.isDestroyed()) return;
  const approxZoom = cameraHeightToApproxZoom(_viewer);
  const shouldShow = approxZoom >= 2.55;
  if (shouldShow && !_h3OutlinesRequested) {
    ensureH3OutlinePrimitives();
  }
  if (_h3OutlinesVisible !== shouldShow) {
    _h3OutlinesVisible = shouldShow;
    for (const prim of _h3OutlineBatches) {
      prim.show = shouldShow;
    }
  }
}

export function initEarthMap({ onInspectSite }) {
  const Cesium = window.Cesium;
  const viewer = createCesiumViewer("earth-map", {
    ellipsoid: Cesium.Ellipsoid.WGS84,
    showAtmosphere: true,
    baseColor: "#071021",
    initialLon: -20,
    initialLat: 28,
    initialZoom: 1.55,
  });
  _viewer = viewer;

  // NASA GIBS EPSG:4326 TileMatrix 3+ aligns cleanly to a 10x5 (36°x36°) GeographicTilingScheme covering -90°..+90°
  const gibsScheme = new Cesium.GeographicTilingScheme({
    numberOfLevelZeroTilesX: 10,
    numberOfLevelZeroTilesY: 5,
  });

  const blueMarbleProvider = new Cesium.WebMapTileServiceImageryProvider({
    url: "https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/BlueMarble_NextGeneration/default/2004-08-01/500m/{TileMatrix}/{TileRow}/{TileCol}.jpeg",
    layer: "BlueMarble_NextGeneration",
    style: "default",
    format: "image/jpeg",
    tileMatrixSetID: "500m",
    tileMatrixLabels: ["3", "4", "5", "6", "7", "8"],
    tilingScheme: gibsScheme,
    tileWidth: 512,
    tileHeight: 512,
    maximumLevel: 5,
    credit: new Cesium.Credit("NASA GIBS / Earthdata"),
  });

  const modisProvider = new Cesium.WebMapTileServiceImageryProvider({
    url: "https://gibs.earthdata.nasa.gov/wmts/epsg4326/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/2024-07-15/250m/{TileMatrix}/{TileRow}/{TileCol}.jpg",
    layer: "MODIS_Terra_CorrectedReflectance_TrueColor",
    style: "default",
    format: "image/jpeg",
    tileMatrixSetID: "250m",
    tileMatrixLabels: ["3", "4", "5", "6", "7", "8", "9"],
    tilingScheme: gibsScheme,
    tileWidth: 512,
    tileHeight: 512,
    maximumLevel: 6,
    credit: new Cesium.Credit("NASA Worldview GIBS"),
  });

  _blueMarbleLayer = viewer.imageryLayers.addImageryProvider(blueMarbleProvider);
  _modisLayer = viewer.imageryLayers.addImageryProvider(modisProvider);
  _modisLayer.show = false;

  _selectedPrimitives = viewer.scene.primitives.add(new Cesium.PrimitiveCollection());
  _topH3Billboards = viewer.scene.primitives.add(new Cesium.BillboardCollection({ scene: viewer.scene }));
  _topH3Labels = viewer.scene.primitives.add(new Cesium.LabelCollection({ scene: viewer.scene }));
  _hotspotBillboards = viewer.scene.primitives.add(new Cesium.BillboardCollection({ scene: viewer.scene }));
  _hotspotLabels = viewer.scene.primitives.add(new Cesium.LabelCollection({ scene: viewer.scene }));

  const beaconColl = viewer.scene.primitives.add(new Cesium.BillboardCollection({ scene: viewer.scene }));
  _beaconBillboard = beaconColl.add({
    image: getPinImages().beacon,
    position: Cesium.Cartesian3.fromDegrees(0, 0, PIN_HEIGHT_M),
    show: false,
    width: 30,
    height: 30,
  });

  viewer.scene.postRender.addEventListener(() => {
    if (_dirtyColorSync) {
      flushPendingColorsToPrimitives();
    }
  });

  viewer.camera.changed.addEventListener(() => {
    syncOutlineVisibilityFromZoom();
    requestAutoSpinFrame();
  });

  const tooltip = document.getElementById("hover-tooltip");
  const mapContainer = document.getElementById("earth-map");
  const mapCanvas = viewer.scene.canvas;

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

  const processHoverFrame = (pos) => {
    const picked = viewer.scene.pick(pos);
    if (picked?.id?.kind === "hotspot") {
      const p = picked.id.props;
      const kind = p.is_well_known ? "Well-Known Baseline" : "Novel Hotspot";
      const key = `hs:${p.id}:${p.score_pct}`;
      const html =
        `<strong>${escapeHtml(p.name)}</strong><br/>` +
        `${escapeHtml(p.country || kind)}<br/>` +
        `Similarity: <b>${escapeHtml(p.score_pct)}%</b>`;
      showTooltip(key, html, pos, "pointer");
      return;
    }
    if (picked?.id?.kind === "top_h3") {
      const p = picked.id.props;
      const key = `pin:${p.id}:${p.rank}:${p.score_pct}`;
      const html =
        `<strong>#${escapeHtml(p.rank)} ${escapeHtml(p.name)}</strong><br/>` +
        `${escapeHtml(p.country)} · Top H3 Region<br/>` +
        `Similarity: <b>${escapeHtml(p.score_pct)}%</b>`;
      showTooltip(key, html, pos, "pointer");
      return;
    }

    const coords = pickGlobeLatLon(viewer, pos);
    if (!coords) {
      hideTooltip();
      return;
    }

    let props = null;
    if (typeof window !== "undefined" && window.h3?.latLngToCell) {
      const h3Id = window.h3.latLngToCell(coords.lat, normalizeLon180(coords.lon), 4);
      props = getSitePropsById().get(h3Id) || null;
    } else if (typeof picked?.id === "string") {
      const baseId = picked.id.split("#")[0];
      props = getSitePropsById().get(baseId) || null;
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
      showTooltip(key, html, pos, "");
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
    const place =
      props.country && props.country !== props.region
        ? `${props.country} (${props.region})`
        : props.region;
    const formattedVal = Number(val).toFixed(1);
    const key = `h3:${props.id}:${formattedVal}:${unitLabel}`;
    const html =
      `<strong>${escapeHtml(props.name)}</strong><br/>` +
      `${escapeHtml(place)}<br/>` +
      `Value: <b>${escapeHtml(formattedVal)}${escapeHtml(unitLabel)}</b>`;
    showTooltip(key, html, pos, "pointer");
  };

  bindCesiumCameraInteraction(viewer, {
    onPointerDown: () => {
      state.pointerDown = true;
      state.userInteracting = true;
      clearTimeout(state.flyToTimer);
      hideTooltip();
    },
    onPointerUp: () => {
      state.pointerDown = false;
      state.userInteracting = false;
      requestAutoSpinFrame();
    },
    onWheelStart: () => {
      state.userInteracting = true;
      clearTimeout(state.flyToTimer);
      hideTooltip();
    },
    onWheelIdle: () => {
      state.userInteracting = false;
      requestAutoSpinFrame();
    },
    onHoverFrame: processHoverFrame,
    onHoverClear: hideTooltip,
    onClick: (pos) => {
      const picked = viewer.scene.pick(pos);
      if (picked?.id?.kind === "hotspot" || picked?.id?.kind === "top_h3") {
        onInspectSite(picked.id.props.id);
        return;
      }
      const coords = pickGlobeLatLon(viewer, pos);
      let cellId = null;
      if (coords && typeof window !== "undefined" && window.h3?.latLngToCell) {
        const candidate = window.h3.latLngToCell(coords.lat, normalizeLon180(coords.lon), 4);
        if (getSitePropsById().has(candidate)) {
          cellId = candidate;
        }
      } else if (typeof picked?.id === "string") {
        cellId = picked.id.split("#")[0];
      }
      if (!cellId) return;
      const val = state.cellDisplayValues[cellId] ?? -999999;
      if (val > -99999) {
        onInspectSite(cellId);
      }
    },
    wheelIdleMs: 2200,
  });

  mapCanvas.addEventListener("mouseleave", hideTooltip);
  window.addEventListener("resize", () => {
    cachedStageW = mapContainer.clientWidth || 800;
    cachedStageH = mapContainer.clientHeight || 600;
  });

  state.map = viewer;
  state.mapReady = true;
  applyBasemap(state.basemap);
  setViewerProjection(viewer, state.isGlobe);
  startBuildingH3FillPrimitives();
  highlightSelectedSiteOnMap(state.selectedSiteId);
  updateEarthMapLayers(true);
  requestAutoSpinFrame();
}

export function resizeEarthMap() {
  if (_viewer && !_viewer.isDestroyed()) {
    _viewer.resize();
  }
}

export function applyBasemap(basemapId) {
  state.basemap = basemapId;
  if (!_viewer || _viewer.isDestroyed() || !_blueMarbleLayer || !_modisLayer) return;
  const useDark = basemapId === "dark_vector";
  const useModis = basemapId === "gibs_modis";

  _blueMarbleLayer.show = !useModis;
  _blueMarbleLayer.brightness = useDark ? 0.25 : 1.0;
  _blueMarbleLayer.saturation = useDark ? 0.08 : 1.0;
  _blueMarbleLayer.alpha = useDark ? 0.88 : 1.0;
  _modisLayer.show = useModis;
}

const _spinController = createAutoSpinController({
  getViewer: () => _viewer,
  shouldSpin: () =>
    Boolean(
      !document.hidden &&
        _viewer &&
        !_viewer.isDestroyed() &&
        state.isGlobe &&
        state.autoSpin &&
        !state.userInteracting &&
        !state.pointerDown &&
        cameraHeightToApproxZoom(_viewer) < 2.8,
    ),
  rateDegPerSec: 2.4,
});

export function requestAutoSpinFrame() {
  _spinController.requestFrame();
}

export function startAutoSpinLoop() {
  _spinController.start();
}

async function ensureRawParameterLoaded(paramId) {
  if (state.rawParamCache[paramId]) return state.rawParamCache[paramId];
  state.rawParamCache[paramId] = await fetchRawParameter(paramId);
  return state.rawParamCache[paramId];
}

function applyAllCellColors({ isScoreLayer, effectiveCutoff, minVal, maxVal, dimWellKnown }) {
  const lut = getPaletteLut(state.palette);
  const invSpan = 1.0 / Math.max(1e-6, maxVal - minVal);
  const isLogScale = state.scaleMode === "log";
  const hexOpacity = state.hexOpacity;
  const tmp = new Uint8Array(4);

  for (const feat of state.earthGeojson.features) {
    const id = feat.properties.id;
    const val = state.cellDisplayValues[id] ?? -999999;
    writeCellRgbaBytes(tmp, {
      val,
      isWellKnown: Boolean(feat.properties.is_well_known),
      isScoreLayer,
      effectiveCutoff,
      hexOpacity,
      minVal,
      maxVal,
      invSpan,
      lut,
      isLogScale,
      dimWellKnown,
    });

    let cached = _rgbaById.get(id);
    if (!cached) {
      cached = new Uint8Array(4);
      _rgbaById.set(id, cached);
    }
    if (
      cached[0] === tmp[0] &&
      cached[1] === tmp[1] &&
      cached[2] === tmp[2] &&
      cached[3] === tmp[3]
    ) {
      continue;
    }
    cached[0] = tmp[0];
    cached[1] = tmp[1];
    cached[2] = tmp[2];
    cached[3] = tmp[3];

    const entries = _cellInstById.get(id);
    if (entries) {
      for (const { prim, instId } of entries) {
        if (prim.ready) {
          const attrs = prim.getGeometryInstanceAttributes(instId);
          if (attrs) {
            attrs.color = cached;
          } else {
            _dirtyColorSync = true;
          }
        } else {
          _dirtyColorSync = true;
        }
      }
    } else {
      _dirtyColorSync = true;
    }
  }
}

export function updateEarthHexOpacity() {
  if (!_viewer || _viewer.isDestroyed() || !state.mapReady || !state.earthGeojson) return;
  const isScoreLayer = !state.activeLayer.startsWith("raw:");
  const effectiveCutoff = isScoreLayer ? state.minScoreFilter : -99999;
  const dimWellKnown = isScoreLayer && state.excludeWellKnown;
  applyAllCellColors({
    isScoreLayer,
    effectiveCutoff,
    minVal: _lastColorRange.minVal,
    maxVal: _lastColorRange.maxVal,
    dimWellKnown,
  });
}

function updatePinCollections({ topH3Results, hotspotResults, minPinScore }) {
  if (!_viewer || _viewer.isDestroyed() || !_topH3Billboards || !_hotspotBillboards) return;
  const Cesium = window.Cesium;
  const imgs = getPinImages();

  _topH3Billboards.removeAll();
  _topH3Labels.removeAll();
  for (let idx = 0; idx < (topH3Results || []).length; idx++) {
    const r = topH3Results[idx];
    if (r.overall_score * 100 < minPinScore) continue;
    const rank = idx + 1;
    const scorePct = Math.round(r.overall_score * 100);
    const isTop3 = rank <= 3;
    const pos = Cesium.Cartesian3.fromDegrees(r.site.lon, r.site.lat, PIN_HEIGHT_M);
    const props = {
      id: r.site.id,
      name: r.site.name,
      country: r.site.country || r.site.region,
      rank,
      score: r.overall_score,
      score_pct: scorePct,
      is_top3: isTop3,
    };
    _topH3Billboards.add({
      id: { kind: "top_h3", props },
      position: pos,
      image: isTop3 ? imgs.top3H3 : imgs.topKH3,
    });
    _topH3Labels.add({
      id: { kind: "top_h3", props },
      position: pos,
      text: `#${rank} ${shortPinTitle(r.site.name)} (${scorePct}%)`,
      font: "600 11px system-ui, -apple-system, sans-serif",
      fillColor: Cesium.Color.fromCssColorString("#ecfeff"),
      outlineColor: Cesium.Color.fromCssColorString("#040812"),
      outlineWidth: 3,
      style: Cesium.LabelStyle.FILL_AND_OUTLINE,
      verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
      pixelOffset: new Cesium.Cartesian2(0, -14),
      distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 2.5e7),
    });
  }

  _hotspotBillboards.removeAll();
  _hotspotLabels.removeAll();
  if (state.showHotspots) {
    for (let idx = 0; idx < (hotspotResults || []).length; idx++) {
      const r = hotspotResults[idx];
      if (r.overall_score * 100 < minPinScore) continue;
      const scorePct = Math.round(r.overall_score * 100);
      const pos = Cesium.Cartesian3.fromDegrees(r.site.lon, r.site.lat, PIN_HEIGHT_M);
      const props = {
        id: r.site.id,
        name: r.site.name,
        country: r.site.country || r.site.region,
        rank: idx + 1,
        is_well_known: r.site.is_well_known,
        score: r.overall_score,
        score_pct: scorePct,
      };
      _hotspotBillboards.add({
        id: { kind: "hotspot", props },
        position: pos,
        image: r.site.is_well_known ? imgs.hsWellKnown : imgs.hsNovel,
      });
      _hotspotLabels.add({
        id: { kind: "hotspot", props },
        position: pos,
        text: `${shortPinTitle(r.site.name)} (${scorePct}%)`,
        font: "500 10.5px system-ui, -apple-system, sans-serif",
        fillColor: Cesium.Color.fromCssColorString(r.site.is_well_known ? "#fde68a" : "#bae6fd"),
        outlineColor: Cesium.Color.fromCssColorString("#040812"),
        outlineWidth: 3,
        style: Cesium.LabelStyle.FILL_AND_OUTLINE,
        verticalOrigin: Cesium.VerticalOrigin.TOP,
        pixelOffset: new Cesium.Cartesian2(0, 12),
        distanceDisplayCondition: new Cesium.DistanceDisplayCondition(0, 1.6e7),
      });
    }
  }
}

export async function updateEarthMapLayers(updateData = true) {
  if (!_viewer || _viewer.isDestroyed() || !state.mapReady || !state.lastRankResponse) {
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
    }
    _displayDataVersion += 1;
  }

  const effectiveCutoff = isScoreLayer ? state.minScoreFilter : -99999;
  const { minVal, midVal, maxVal, rawMin, rawMax, isClipped, validCount } = computeLayerColorRange({
    features: state.earthGeojson.features,
    cellDisplayValues: state.cellDisplayValues,
    isScoreLayer,
    effectiveCutoff,
    scaleMode: state.scaleMode,
    paramSpec,
    dataVersion: _displayDataVersion,
  });
  _lastColorRange = { minVal, maxVal };

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

  const dimWellKnown = isScoreLayer && state.excludeWellKnown;
  applyAllCellColors({
    isScoreLayer,
    effectiveCutoff,
    minVal,
    maxVal,
    dimWellKnown,
  });

  const minPinScore = isScoreLayer ? state.minScoreFilter : 0;
  updatePinCollections({
    topH3Results: top_h3_results,
    hotspotResults: hotspot_results,
    minPinScore,
  });
}
