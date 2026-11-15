// Shared CesiumJS Viewer, camera, picking, projection & auto-spin utilities

import { prefersReducedMotion } from "../ui/dom.js";

const DEFAULT_RADIUS_M = 6371000;

export function getEllipsoidRadiusMeters(viewer) {
  return viewer?.scene?.globe?.ellipsoid?.maximumRadius || DEFAULT_RADIUS_M;
}

export function maplibreZoomToCameraHeightMeters(zoom, radiusMeters = DEFAULT_RADIUS_M) {
  const z = Number.isFinite(zoom) ? zoom : 1.55;
  const minHeight = Math.max(500, radiusMeters * 0.0005);
  return Math.max(minHeight, radiusMeters * 3.1 * Math.pow(0.5, z - 1.55));
}

export function getEffectiveCameraSpanMeters(viewer) {
  if (!viewer || viewer.isDestroyed()) return DEFAULT_RADIUS_M * 3.1;
  const Cesium = window.Cesium;
  const radiusMeters = getEllipsoidRadiusMeters(viewer);
  const minHeight = Math.max(500, radiusMeters * 0.0005);
  if (Cesium && viewer.scene.mode === Cesium.SceneMode.SCENE2D) {
    const frustum = viewer.camera.frustum;
    const width = Math.abs((frustum.right ?? 1) - (frustum.left ?? -1));
    const height2d = Math.abs((frustum.top ?? 1) - (frustum.bottom ?? -1));
    const span = Math.max(width, height2d);
    if (Number.isFinite(span) && span > 0) {
      return Math.max(minHeight, span * 0.5);
    }
  }
  const pos = viewer.camera.positionCartographic;
  return pos ? Math.max(minHeight, pos.height) : radiusMeters * 3.1;
}

export function cameraHeightToApproxZoom(viewer) {
  if (!viewer || viewer.isDestroyed()) return 1.55;
  const radiusMeters = getEllipsoidRadiusMeters(viewer);
  const height = getEffectiveCameraSpanMeters(viewer);
  return 1.55 + Math.log2((radiusMeters * 3.1) / height);
}

export function createCesiumViewer(
  containerId,
  {
    ellipsoid = null,
    showAtmosphere = true,
    baseColor = "#071021",
    initialLon = -20,
    initialLat = 28,
    initialZoom = 1.55,
  } = {},
) {
  const Cesium = window.Cesium;
  if (!Cesium) {
    throw new Error("CesiumJS library failed to load.");
  }
  if (Cesium.Ion) {
    Cesium.Ion.defaultAccessToken = "";
  }

  const targetEllipsoid = ellipsoid || Cesium.Ellipsoid.WGS84;
  const mapProjection = new Cesium.GeographicProjection(targetEllipsoid);
  const viewer = new Cesium.Viewer(containerId, {
    baseLayer: false,
    baseLayerPicker: false,
    geocoder: false,
    timeline: false,
    animation: false,
    homeButton: false,
    sceneModePicker: false,
    navigationHelpButton: false,
    fullscreenButton: false,
    infoBox: false,
    selectionIndicator: false,
    skyBox: false,
    sun: false,
    moon: false,
    ellipsoid: targetEllipsoid,
    mapProjection,
    skyAtmosphere: showAtmosphere ? new Cesium.SkyAtmosphere(targetEllipsoid) : false,
    terrainProvider: new Cesium.EllipsoidTerrainProvider({ ellipsoid: targetEllipsoid }),
    globe: new Cesium.Globe(targetEllipsoid),
    contextOptions: {
      webgl: {
        alpha: true,
        antialias: true,
      },
    },
    scene3DOnly: false,
    useBrowserRecommendedResolution: true,
  });

  const { scene, camera } = viewer;
  scene.backgroundColor = Cesium.Color.TRANSPARENT;
  scene.globe.baseColor = Cesium.Color.fromCssColorString(baseColor);
  scene.globe.enableLighting = false;
  scene.globe.showGroundAtmosphere = Boolean(showAtmosphere);
  scene.globe.depthTestAgainstTerrain = false;

  const ctrl = scene.screenSpaceCameraController;
  ctrl.enableZoom = true;
  ctrl.minimumZoomDistance = targetEllipsoid.maximumRadius * 0.0005;
  ctrl.maximumZoomDistance = targetEllipsoid.maximumRadius * 8.0;
  ctrl.enableLook = false;
  camera.percentageChanged = 0.02;

  const startHeight = maplibreZoomToCameraHeightMeters(initialZoom, targetEllipsoid.maximumRadius);
  camera.setView({
    destination: Cesium.Cartesian3.fromDegrees(initialLon, initialLat, startHeight, targetEllipsoid),
  });

  return viewer;
}

export function setViewerProjection(viewer, isGlobe) {
  if (!viewer || viewer.isDestroyed()) return;
  const Cesium = window.Cesium;
  const targetMode = isGlobe ? Cesium.SceneMode.SCENE3D : Cesium.SceneMode.SCENE2D;
  if (viewer.scene.mode === targetMode) return;
  if (isGlobe) {
    viewer.scene.morphTo3D(0);
  } else {
    viewer.scene.morphTo2D(0);
  }
}

export function flyToLatLon(viewer, { lon, lat, zoom = 3.2, durationSec = 1.25 } = {}) {
  if (!viewer || viewer.isDestroyed()) return;
  const Cesium = window.Cesium;
  const ellipsoid = viewer.scene.globe.ellipsoid;
  const height = maplibreZoomToCameraHeightMeters(zoom, ellipsoid.maximumRadius);
  const clampedLat = Math.max(-89.99, Math.min(89.99, lat));
  if (typeof viewer.camera.cancelFlight === "function") {
    viewer.camera.cancelFlight();
  }
  const flyOpts = {
    destination: Cesium.Cartesian3.fromDegrees(lon, clampedLat, height, ellipsoid),
    duration: prefersReducedMotion() ? 0 : durationSec,
  };
  if (viewer.scene.mode !== Cesium.SceneMode.SCENE2D) {
    flyOpts.orientation = {
      heading: 0,
      pitch: -Cesium.Math.PI_OVER_TWO,
      roll: 0,
    };
  }
  viewer.camera.flyTo(flyOpts);
}

export function zoomViewerByFactor(viewer, factor = 1.55) {
  if (!viewer || viewer.isDestroyed() || !Number.isFinite(factor) || factor <= 0 || factor === 1) return;
  const Cesium = window.Cesium;
  if (typeof viewer.camera.cancelFlight === "function") {
    viewer.camera.cancelFlight();
  }
  const ctrl = viewer.scene.screenSpaceCameraController;
  const radius = getEllipsoidRadiusMeters(viewer);
  const minDist = ctrl?.minimumZoomDistance ?? radius * 0.0005;
  const maxDist = ctrl?.maximumZoomDistance ?? radius * 8.0;

  if (viewer.scene.mode === Cesium.SceneMode.SCENE2D) {
    const frustum = viewer.camera.frustum;
    const width = Math.abs((frustum.right ?? 1) - (frustum.left ?? -1));
    const height2d = Math.abs((frustum.top ?? 1) - (frustum.bottom ?? -1));
    const span = Math.max(100, width, height2d);
    const minSpan = Math.max(1000, minDist * 2.0);
    const maxSpan = radius * 12.0;
    const target = Math.max(minSpan, Math.min(maxSpan, span / factor));
    if (factor > 1) {
      const delta = span - target;
      if (delta > 0) viewer.camera.zoomIn(delta);
    } else {
      const delta = target - span;
      if (delta > 0) viewer.camera.zoomOut(delta);
    }
    return;
  }

  const carto = viewer.camera.positionCartographic;
  const height = carto ? Math.max(100, carto.height) : radius * 2.5;
  const targetHeight = Math.max(minDist, Math.min(maxDist, height / factor));
  if (factor > 1) {
    const delta = height - targetHeight;
    if (delta > 0) viewer.camera.zoomIn(delta);
  } else {
    const delta = targetHeight - height;
    if (delta > 0) viewer.camera.zoomOut(delta);
  }
}

export function pickGlobeLatLon(viewer, screenPos) {
  if (!viewer || viewer.isDestroyed() || !screenPos) return null;
  const Cesium = window.Cesium;
  try {
    const ellipsoid = viewer.scene.globe.ellipsoid;
    const cartesian = viewer.camera.pickEllipsoid(screenPos, ellipsoid);
    if (!cartesian) return null;
    const carto = Cesium.Cartographic.fromCartesian(cartesian, ellipsoid);
    if (!carto) return null;
    const lat = Cesium.Math.toDegrees(carto.latitude);
    const lon = Cesium.Math.toDegrees(carto.longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
    return { lat, lon };
  } catch {
    return null;
  }
}

export function createAutoSpinController({ getViewer, shouldSpin, rateDegPerSec = 2.4 }) {
  let rafId = 0;
  let lastTime = 0;
  let visibilityBound = false;

  function tick(now) {
    rafId = 0;
    const viewer = getViewer();
    if (!viewer || viewer.isDestroyed() || !shouldSpin()) return;
    const dt = Math.min(0.1, (now - lastTime) / 1000.0);
    lastTime = now;
    const Cesium = window.Cesium;
    viewer.camera.rotate(Cesium.Cartesian3.UNIT_Z, -Cesium.Math.toRadians(dt * rateDegPerSec));
    rafId = requestAnimationFrame(tick);
  }

  function requestFrame() {
    if (!rafId && shouldSpin()) {
      lastTime = performance.now();
      rafId = requestAnimationFrame(tick);
    }
  }

  function start() {
    if (!visibilityBound && typeof document !== "undefined") {
      visibilityBound = true;
      document.addEventListener("visibilitychange", () => {
        if (!document.hidden) requestFrame();
      });
    }
    requestFrame();
  }

  return { requestFrame, start };
}

export function makePinDataUrl({ fill, stroke = "#ffffff", radius = 8, strokeWidth = 2, glow = false } = {}) {
  const pad = glow ? 8 : 3;
  const size = (radius + strokeWidth + pad) * 2;
  const c = size / 2;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");

  if (glow) {
    const grad = ctx.createRadialGradient(c, c, radius * 0.4, c, c, radius + pad);
    grad.addColorStop(0, `${fill}99`);
    grad.addColorStop(1, `${fill}00`);
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(c, c, radius + pad, 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.beginPath();
  ctx.arc(c, c, radius, 0, Math.PI * 2);
  ctx.fillStyle = fill;
  ctx.fill();
  ctx.lineWidth = strokeWidth;
  ctx.strokeStyle = stroke;
  ctx.stroke();

  return canvas.toDataURL("image/png");
}

/**
 * Bind standard Cesium camera pointer/wheel interaction, RAF-throttled hover, and click dispatch.
 * Consolidates shared interaction handling across the Earth and Planetary globes.
 */
export function bindCesiumCameraInteraction(
  viewer,
  {
    onPointerDown,
    onPointerUp,
    onWheelStart,
    onWheelIdle,
    onHoverFrame,
    onHoverClear,
    onClick,
    wheelIdleMs = 2000,
  } = {},
) {
  const Cesium = window.Cesium;
  const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
  let hoverRafId = 0;
  let pendingPos = null;
  let wheelTimeout = 0;
  let isDown = false;

  const cancelHover = () => {
    pendingPos = null;
    if (hoverRafId) {
      cancelAnimationFrame(hoverRafId);
      hoverRafId = 0;
    }
    onHoverClear?.();
  };

  const handleDown = () => {
    isDown = true;
    viewer.camera.cancelFlight?.();
    cancelHover();
    onPointerDown?.();
  };

  const handleUp = () => {
    isDown = false;
    onPointerUp?.();
  };

  handler.setInputAction(handleDown, Cesium.ScreenSpaceEventType.LEFT_DOWN);
  handler.setInputAction(handleUp, Cesium.ScreenSpaceEventType.LEFT_UP);
  handler.setInputAction(handleDown, Cesium.ScreenSpaceEventType.RIGHT_DOWN);
  handler.setInputAction(handleUp, Cesium.ScreenSpaceEventType.RIGHT_UP);

  handler.setInputAction(() => {
    viewer.camera.cancelFlight?.();
    cancelHover();
    onWheelStart?.();
    clearTimeout(wheelTimeout);
    wheelTimeout = setTimeout(() => {
      if (!isDown) {
        onWheelIdle?.();
      }
    }, wheelIdleMs);
  }, Cesium.ScreenSpaceEventType.WHEEL);

  handler.setInputAction((movement) => {
    if (isDown) {
      cancelHover();
      return;
    }
    pendingPos = Cesium.Cartesian2.clone(movement.endPosition, pendingPos);
    if (!hoverRafId) {
      hoverRafId = requestAnimationFrame(() => {
        hoverRafId = 0;
        const pos = pendingPos;
        pendingPos = null;
        if (!pos || isDown || viewer.isDestroyed()) return;
        onHoverFrame?.(pos);
      });
    }
  }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

  handler.setInputAction((click) => {
    onClick?.(click.position);
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

  return {
    handler,
    destroy() {
      clearTimeout(wheelTimeout);
      cancelHover();
      if (!handler.isDestroyed()) {
        handler.destroy();
      }
    },
  };
}
