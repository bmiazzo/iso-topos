// Reusable pointer + keyboard resize controllers for sidebars, collapsible menus, and globe overlays

import { RESIZE_STORAGE_KEY } from "../state.js";

function loadResizeStore(storage) {
  try {
    const raw = storage?.getItem(RESIZE_STORAGE_KEY);
    if (!raw) return { sidebars: {}, menus: {}, overlays: {} };
    const parsed = JSON.parse(raw);
    return {
      sidebars: parsed?.sidebars && typeof parsed.sidebars === "object" ? parsed.sidebars : {},
      menus: parsed?.menus && typeof parsed.menus === "object" ? parsed.menus : {},
      overlays: parsed?.overlays && typeof parsed.overlays === "object" ? parsed.overlays : {},
    };
  } catch {
    return { sidebars: {}, menus: {}, overlays: {} };
  }
}

function saveResizeStore(storage, store) {
  try {
    storage?.setItem(RESIZE_STORAGE_KEY, JSON.stringify(store));
  } catch {
    // Ignore storage quota or private-browsing errors
  }
}

function clamp(val, min, max) {
  if (max < min) return min;
  return Math.max(min, Math.min(max, Math.round(val)));
}

function bindDragSession(handleEl, { cursor, onStart, onMove, onEnd, onReset }) {
  if (!handleEl || handleEl.dataset.resizeBound === "1") return;
  handleEl.dataset.resizeBound = "1";

  handleEl.addEventListener("click", (e) => {
    e.stopPropagation();
  });

  handleEl.addEventListener("dblclick", (e) => {
    e.preventDefault();
    e.stopPropagation();
    onReset?.();
  });

  handleEl.addEventListener("pointerdown", (e) => {
    if (e.button !== undefined && e.button !== 0 && e.pointerType === "mouse") return;
    e.preventDefault();
    e.stopPropagation();

    const startCtx = onStart?.(e) || {};
    handleEl.classList.add("is-active");
    document.body.classList.add("is-resizing-ui");
    const prevCursor = document.body.style.cursor;
    document.body.style.cursor = cursor;

    try {
      handleEl.setPointerCapture?.(e.pointerId);
    } catch {
      // Ignore synthetic events without active pointerId
    }

    const handleMove = (moveEvt) => {
      onMove?.(moveEvt, startCtx);
    };

    const cleanup = (endEvt) => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", cleanup);
      window.removeEventListener("pointercancel", cleanup);
      handleEl.classList.remove("is-active");
      document.body.classList.remove("is-resizing-ui");
      document.body.style.cursor = prevCursor;
      try {
        if (handleEl.hasPointerCapture?.(e.pointerId)) {
          handleEl.releasePointerCapture(e.pointerId);
        }
      } catch {
        // Ignore release errors
      }
      onEnd?.(endEvt, startCtx);
    };

    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", cleanup);
    window.addEventListener("pointercancel", cleanup);
  });
}

export class SidebarResizeController {
  constructor({ workspaceEl, specs = [], storage = window.localStorage, onLayoutChange = null }) {
    this.workspaceEl = workspaceEl;
    this.specs = specs;
    this.storage = storage;
    this.onLayoutChange = onLayoutChange;
    this.store = loadResizeStore(storage);
    this._rafId = 0;
  }

  _notifyLayout({ immediate = false } = {}) {
    if (!this.onLayoutChange) return;
    if (immediate) {
      this.onLayoutChange();
      return;
    }
    if (this._rafId) return;
    this._rafId = requestAnimationFrame(() => {
      this._rafId = 0;
      this.onLayoutChange();
    });
  }

  _getMaxAllowed(spec) {
    if (!this.workspaceEl) return spec.maxWidth;
    const totalW = this.workspaceEl.clientWidth;
    if (!totalW) return spec.maxWidth;

    let oppositeW = 0;
    if (spec.oppositeCssVar) {
      const oppositeCollapsed =
        spec.oppositeCollapsedClass && this.workspaceEl.classList.contains(spec.oppositeCollapsedClass);
      if (!oppositeCollapsed) {
        const raw = getComputedStyle(this.workspaceEl).getPropertyValue(spec.oppositeCssVar);
        oppositeW = parseFloat(raw) || spec.oppositeDefault || 0;
      }
    }
    const minCenter = spec.minCenterWidth ?? 260;
    const resizerAllowance = 12;
    return Math.min(spec.maxWidth, Math.max(spec.minWidth, totalW - oppositeW - minCenter - resizerAllowance));
  }

  _getCurrentWidth(spec) {
    if (!this.workspaceEl) return spec.defaultWidth;
    const raw = getComputedStyle(this.workspaceEl).getPropertyValue(spec.cssVar);
    const parsed = parseFloat(raw);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : spec.defaultWidth;
  }

  _applyWidth(spec, width, { persist = false, notify = true } = {}) {
    if (!this.workspaceEl) return width;
    const maxAllowed = this._getMaxAllowed(spec);
    const clamped = clamp(width, spec.minWidth, maxAllowed);
    this.workspaceEl.style.setProperty(spec.cssVar, `${clamped}px`);
    if (spec.handleEl) {
      spec.handleEl.setAttribute("aria-valuemin", String(spec.minWidth));
      spec.handleEl.setAttribute("aria-valuemax", String(Math.round(maxAllowed)));
      spec.handleEl.setAttribute("aria-valuenow", String(clamped));
    }
    if (persist) {
      this.store.sidebars[spec.key] = clamped;
      saveResizeStore(this.storage, this.store);
    }
    if (notify) this._notifyLayout();
    return clamped;
  }

  _resetWidth(spec) {
    if (!this.workspaceEl) return;
    this.workspaceEl.style.removeProperty(spec.cssVar);
    delete this.store.sidebars[spec.key];
    saveResizeStore(this.storage, this.store);
    if (spec.handleEl) {
      spec.handleEl.setAttribute("aria-valuenow", String(spec.defaultWidth));
    }
    this._notifyLayout({ immediate: true });
  }

  init() {
    if (!this.workspaceEl) return;

    for (const spec of this.specs) {
      const saved = Number(this.store.sidebars?.[spec.key]);
      if (Number.isFinite(saved) && saved >= spec.minWidth) {
        this._applyWidth(spec, saved, { persist: false, notify: false });
      } else if (spec.handleEl) {
        spec.handleEl.setAttribute("aria-valuemin", String(spec.minWidth));
        spec.handleEl.setAttribute("aria-valuemax", String(spec.maxWidth));
        spec.handleEl.setAttribute("aria-valuenow", String(spec.defaultWidth));
      }

      const { handleEl } = spec;
      if (!handleEl) continue;

      bindDragSession(handleEl, {
        cursor: "col-resize",
        onStart: (e) => {
          this.workspaceEl.classList.add("is-resizing");
          return {
            startX: e.clientX,
            startWidth: this._getCurrentWidth(spec),
            lastWidth: this._getCurrentWidth(spec),
          };
        },
        onMove: (e, ctx) => {
          const dx = e.clientX - ctx.startX;
          const next = spec.side === "left" ? ctx.startWidth + dx : ctx.startWidth - dx;
          ctx.lastWidth = this._applyWidth(spec, next, { persist: false, notify: true });
        },
        onEnd: (_e, ctx) => {
          this.workspaceEl.classList.remove("is-resizing");
          if (Number.isFinite(ctx.lastWidth)) {
            this.store.sidebars[spec.key] = ctx.lastWidth;
            saveResizeStore(this.storage, this.store);
          }
          this._notifyLayout({ immediate: true });
        },
        onReset: () => this._resetWidth(spec),
      });

      handleEl.addEventListener("keydown", (e) => {
        const step = e.shiftKey ? 48 : 16;
        const dir = spec.side === "left" ? 1 : -1;
        if (e.key === "ArrowRight") {
          e.preventDefault();
          this._applyWidth(spec, this._getCurrentWidth(spec) + step * dir, { persist: true, notify: true });
        } else if (e.key === "ArrowLeft") {
          e.preventDefault();
          this._applyWidth(spec, this._getCurrentWidth(spec) - step * dir, { persist: true, notify: true });
        } else if (e.key === "Home") {
          e.preventDefault();
          this._applyWidth(spec, spec.minWidth, { persist: true, notify: true });
        } else if (e.key === "End") {
          e.preventDefault();
          this._applyWidth(spec, this._getMaxAllowed(spec), { persist: true, notify: true });
        } else if (e.key === "Enter" || e.key === "0") {
          e.preventDefault();
          this._resetWidth(spec);
        }
      });
    }

    window.addEventListener("resize", () => {
      for (const spec of this.specs) {
        if (spec.key in (this.store.sidebars || {})) {
          this._applyWidth(spec, this._getCurrentWidth(spec), { persist: false, notify: false });
        }
      }
    });
  }
}

export class MenuResizeController {
  constructor({ storage = window.localStorage, onMenuResize = null } = {}) {
    this.storage = storage;
    this.onMenuResize = onMenuResize;
    this.store = loadResizeStore(storage);
  }

  _getMenuTitle(el) {
    const titleEl = el.querySelector(
      ":scope > .collapse-trigger .collapse-title, :scope > .collapse-header-row .collapse-title, h3, .detail-site-title"
    );
    return titleEl?.textContent?.trim() || "menu";
  }

  _applyHeight(el, id, cssVar, height, { minHeight, maxHeight, persist = false } = {}) {
    const clamped = clamp(height, minHeight, maxHeight);
    el.classList.add("is-resized");
    el.style.setProperty(cssVar, `${clamped}px`);
    const handle = el.querySelector(":scope > .menu-resize-handle");
    if (handle) {
      handle.setAttribute("aria-valuemin", String(minHeight));
      handle.setAttribute("aria-valuemax", String(maxHeight));
      handle.setAttribute("aria-valuenow", String(clamped));
    }
    if (persist && id) {
      this.store.menus[id] = clamped;
      saveResizeStore(this.storage, this.store);
    }
    this.onMenuResize?.(id, el);
    return clamped;
  }

  _resetHeight(el, id, cssVar) {
    el.classList.remove("is-resized");
    el.style.removeProperty(cssVar);
    if (id) {
      delete this.store.menus[id];
      saveResizeStore(this.storage, this.store);
    }
    const handle = el.querySelector(":scope > .menu-resize-handle");
    handle?.removeAttribute("aria-valuenow");
    this.onMenuResize?.(id, el);
  }

  _attachVerticalHandle(el, { id, cssVar, measureEl, minHeight = 72, maxHeight = 760 }) {
    if (!el || el.dataset.menuResizeBound === "1") return;
    el.dataset.menuResizeBound = "1";
    el.classList.add("is-resizable");

    const saved = Number(this.store.menus?.[id]);
    if (Number.isFinite(saved) && saved >= minHeight) {
      this._applyHeight(el, id, cssVar, saved, { minHeight, maxHeight, persist: false });
    }

    const handle = document.createElement("div");
    handle.className = "menu-resize-handle";
    handle.setAttribute("role", "separator");
    handle.setAttribute("tabindex", "0");
    handle.setAttribute("aria-orientation", "horizontal");
    handle.setAttribute("aria-label", `Resize ${this._getMenuTitle(el)} height`);
    handle.setAttribute("aria-valuemin", String(minHeight));
    handle.setAttribute("aria-valuemax", String(maxHeight));
    if (Number.isFinite(saved) && saved >= minHeight) {
      handle.setAttribute("aria-valuenow", String(Math.round(saved)));
    }
    handle.title = "Drag to resize height · Double-click to reset";
    el.appendChild(handle);

    const getDynamicMax = () => Math.max(minHeight, Math.min(maxHeight, Math.round(window.innerHeight * 0.78)));

    bindDragSession(handle, {
      cursor: "row-resize",
      onStart: (e) => {
        el.classList.add("is-resizing");
        const target = measureEl() || el;
        const startHeight = Math.max(minHeight, target.getBoundingClientRect().height);
        return { startY: e.clientY, startHeight, lastHeight: startHeight };
      },
      onMove: (e, ctx) => {
        const dy = e.clientY - ctx.startY;
        ctx.lastHeight = this._applyHeight(el, id, cssVar, ctx.startHeight + dy, {
          minHeight,
          maxHeight: getDynamicMax(),
          persist: false,
        });
      },
      onEnd: (_e, ctx) => {
        el.classList.remove("is-resizing");
        if (id && Number.isFinite(ctx.lastHeight)) {
          this.store.menus[id] = ctx.lastHeight;
          saveResizeStore(this.storage, this.store);
        }
        this.onMenuResize?.(id, el);
      },
      onReset: () => this._resetHeight(el, id, cssVar),
    });

    handle.addEventListener("keydown", (e) => {
      const step = e.shiftKey ? 40 : 16;
      const dynMax = getDynamicMax();
      const target = measureEl() || el;
      const curHeight = Math.round(target.getBoundingClientRect().height || minHeight);
      if (e.key === "ArrowDown") {
        e.preventDefault();
        this._applyHeight(el, id, cssVar, curHeight + step, {
          minHeight,
          maxHeight: dynMax,
          persist: true,
        });
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        this._applyHeight(el, id, cssVar, curHeight - step, {
          minHeight,
          maxHeight: dynMax,
          persist: true,
        });
      } else if (e.key === "Enter" || e.key === "0") {
        e.preventDefault();
        this._resetHeight(el, id, cssVar);
      }
    });
  }

  registerContainer(root = document) {
    // Level-1 & Level-2 collapsible menus (excluding Level-3 dimension groups and floating overlays)
    const menus = root.querySelectorAll(".collapsible-menu[data-collapse-id]");
    for (const menuEl of menus) {
      if (menuEl.classList.contains("menu-level-3") || menuEl.hasAttribute("data-resize-overlay")) continue;
      const id = menuEl.dataset.collapseId;
      this._attachVerticalHandle(menuEl, {
        id,
        cssVar: "--menu-body-height",
        measureEl: () => menuEl.querySelector(":scope > .collapse-body > .collapse-inner"),
        minHeight: 72,
        maxHeight: 760,
      });
    }
  }
}

export class OverlayResizeController {
  constructor({ stageEl = null, storage = window.localStorage } = {}) {
    this.stageEl = stageEl;
    this.storage = storage;
    this.store = loadResizeStore(storage);
  }

  _getBounds(overlayEl) {
    const stageW = this.stageEl?.clientWidth || window.innerWidth;
    const stageH = this.stageEl?.clientHeight || window.innerHeight;
    return {
      minW: 196,
      maxW: Math.max(240, Math.min(560, stageW - 74)),
      minH: 108,
      maxH: Math.max(150, Math.min(620, stageH - 64)),
    };
  }

  _applyOverlaySize(overlayEl, id, { width, height }, { persist = false } = {}) {
    const bounds = this._getBounds(overlayEl);
    const isCollapsible = overlayEl.classList.contains("collapsible-menu");
    const saved = this.store.overlays[id] || {};

    if (width !== undefined) {
      if (width === null) {
        overlayEl.classList.remove("is-resized-w");
        overlayEl.style.removeProperty("--overlay-width");
        delete saved.width;
      } else {
        const w = clamp(width, bounds.minW, bounds.maxW);
        overlayEl.classList.add("is-resized-w");
        overlayEl.style.setProperty("--overlay-width", `${w}px`);
        saved.width = w;
      }
    }

    if (height !== undefined) {
      if (height === null) {
        overlayEl.classList.remove("is-resized-h");
        overlayEl.style.removeProperty("--overlay-height");
        delete saved.height;
      } else {
        const h = clamp(height, bounds.minH, bounds.maxH);
        overlayEl.classList.add("is-resized-h");
        overlayEl.style.setProperty("--overlay-height", `${h}px`);
        saved.height = h;
      }
    }

    if (persist) {
      if (Object.keys(saved).length === 0) {
        delete this.store.overlays[id];
      } else {
        this.store.overlays[id] = saved;
      }
      saveResizeStore(this.storage, this.store);
    }

    if (!isCollapsible && saved.height === undefined) {
      overlayEl.style.removeProperty("--overlay-height");
    }
  }

  _createEdgeHandle(overlayEl, id, { axis, anchor }) {
    const handle = document.createElement("div");
    const isBottomAnchored = anchor === "bottom-left";
    const isCorner = axis === "both";
    const isHeight = axis === "y";

    let dirClass = "overlay-resizer-e";
    let cursor = "ew-resize";
    let label = "Resize overlay width";
    if (isHeight) {
      dirClass = isBottomAnchored ? "overlay-resizer-n" : "overlay-resizer-s";
      cursor = "ns-resize";
      label = "Resize overlay height";
    } else if (isCorner) {
      dirClass = isBottomAnchored ? "overlay-resizer-ne" : "overlay-resizer-se";
      cursor = isBottomAnchored ? "nesw-resize" : "nwse-resize";
      label = "Resize overlay width and height";
    }

    handle.className = `overlay-resizer ${dirClass}`;
    handle.setAttribute("role", "separator");
    handle.setAttribute("tabindex", "0");
    handle.setAttribute("aria-orientation", isHeight ? "horizontal" : "vertical");
    handle.setAttribute("aria-label", label);
    handle.title = "Drag to resize · Double-click to reset";

    const getHeightTarget = () =>
      overlayEl.classList.contains("collapsible-menu")
        ? overlayEl.querySelector(":scope > .collapse-body > .collapse-inner") || overlayEl
        : overlayEl;

    bindDragSession(handle, {
      cursor,
      onStart: (e) => {
        overlayEl.classList.add("is-resizing");
        const rectW = overlayEl.getBoundingClientRect().width;
        const rectH = getHeightTarget().getBoundingClientRect().height;
        return {
          startX: e.clientX,
          startY: e.clientY,
          startW: rectW,
          startH: rectH,
        };
      },
      onMove: (e, ctx) => {
        const dx = e.clientX - ctx.startX;
        const dy = e.clientY - ctx.startY;
        const update = {};
        if (axis === "x" || axis === "both") {
          update.width = ctx.startW + dx;
        }
        if (axis === "y" || axis === "both") {
          update.height = isBottomAnchored ? ctx.startH - dy : ctx.startH + dy;
        }
        this._applyOverlaySize(overlayEl, id, update, { persist: false });
      },
      onEnd: () => {
        overlayEl.classList.remove("is-resizing");
        const current = {};
        if (overlayEl.classList.contains("is-resized-w")) {
          current.width = parseFloat(overlayEl.style.getPropertyValue("--overlay-width"));
        }
        if (overlayEl.classList.contains("is-resized-h")) {
          current.height = parseFloat(overlayEl.style.getPropertyValue("--overlay-height"));
        }
        if (Object.keys(current).length > 0) {
          this.store.overlays[id] = current;
          saveResizeStore(this.storage, this.store);
        }
      },
      onReset: () => {
        this._applyOverlaySize(overlayEl, id, { width: null, height: null }, { persist: true });
      },
    });

    handle.addEventListener("keydown", (e) => {
      const step = e.shiftKey ? 36 : 14;
      const curW = overlayEl.getBoundingClientRect().width;
      const curH = getHeightTarget().getBoundingClientRect().height;
      const hSign = isBottomAnchored ? -1 : 1;

      if ((axis === "x" || axis === "both") && (e.key === "ArrowRight" || e.key === "ArrowLeft")) {
        e.preventDefault();
        const delta = e.key === "ArrowRight" ? step : -step;
        this._applyOverlaySize(overlayEl, id, { width: curW + delta }, { persist: true });
      } else if ((axis === "y" || axis === "both") && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
        e.preventDefault();
        const delta = (e.key === "ArrowDown" ? step : -step) * hSign;
        this._applyOverlaySize(overlayEl, id, { height: curH + delta }, { persist: true });
      } else if (e.key === "Enter" || e.key === "0") {
        e.preventDefault();
        this._applyOverlaySize(overlayEl, id, { width: null, height: null }, { persist: true });
      }
    });

    return handle;
  }

  registerContainer(root = document) {
    const overlays = root.querySelectorAll("[data-resize-overlay]");
    for (const overlayEl of overlays) {
      if (overlayEl.dataset.overlayResizeBound === "1") continue;
      overlayEl.dataset.overlayResizeBound = "1";
      overlayEl.classList.add("is-resizable-overlay");

      const id = overlayEl.dataset.resizeOverlay;
      const anchor = overlayEl.dataset.resizeAnchor || "top-left";
      const saved = this.store.overlays?.[id];
      if (saved && (Number.isFinite(saved.width) || Number.isFinite(saved.height))) {
        this._applyOverlaySize(
          overlayEl,
          id,
          {
            width: Number.isFinite(saved.width) ? saved.width : undefined,
            height: Number.isFinite(saved.height) ? saved.height : undefined,
          },
          { persist: false }
        );
      }

      overlayEl.append(
        this._createEdgeHandle(overlayEl, id, { axis: "x", anchor }),
        this._createEdgeHandle(overlayEl, id, { axis: "y", anchor }),
        this._createEdgeHandle(overlayEl, id, { axis: "both", anchor })
      );
    }
  }
}
