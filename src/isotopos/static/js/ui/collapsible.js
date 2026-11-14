// Reusable declarative collapsible menu factory, accordion controller & sidebar manager

import { COLLAPSE_STORAGE_KEY } from "../state.js";

const CHEVRON_SVG = `
  <svg viewBox="0 0 12 12" fill="none" aria-hidden="true">
    <path d="M2.5 4.25L6 7.75L9.5 4.25" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
  </svg>
`;

const LEVEL_CLASS = {
  1: "panel-section menu-level-1",
  2: "nested-group menu-level-2",
  3: "dim-group menu-level-3",
};

function loadPersistedStore(storage) {
  try {
    const raw = storage?.getItem(COLLAPSE_STORAGE_KEY);
    if (!raw) return { panels: {}, sidebars: { left: false, right: false } };
    const parsed = JSON.parse(raw);
    return {
      panels: parsed?.panels && typeof parsed.panels === "object" ? parsed.panels : {},
      sidebars: {
        left: Boolean(parsed?.sidebars?.left),
        right: Boolean(parsed?.sidebars?.right),
      },
    };
  } catch {
    return { panels: {}, sidebars: { left: false, right: false } };
  }
}

function savePersistedStore(storage, store) {
  try {
    storage?.setItem(COLLAPSE_STORAGE_KEY, JSON.stringify(store));
  } catch {
    // Ignore storage quota or private-browsing errors
  }
}

/**
 * Declarative factory for creating a collapsible menu at Level 1, 2, or 3.
 * Makes adding new sections, dimension groups, or nested overlays trivial.
 */
export function createCollapsibleSection({
  id,
  title,
  level = 2,
  defaultOpen = false,
  summaryId = null,
  summaryText = "",
  summaryVariant = "neutral",
  contentEl = null,
  extraClasses = "",
}) {
  const wrapper = document.createElement("section");
  const levelClass = LEVEL_CLASS[level] || LEVEL_CLASS[2];
  wrapper.className = `collapsible-menu ${levelClass} ${extraClasses}`.trim();
  wrapper.dataset.collapseId = id;
  wrapper.dataset.collapseDefault = defaultOpen ? "open" : "closed";

  const bodyId = `collapse-body-${id}`;
  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "collapse-trigger";
  trigger.setAttribute("aria-expanded", defaultOpen ? "true" : "false");
  trigger.setAttribute("aria-controls", bodyId);

  const titleWrap = document.createElement("span");
  titleWrap.className = "collapse-title-wrap";
  const chevron = document.createElement("span");
  chevron.className = "chevron";
  chevron.innerHTML = CHEVRON_SVG;
  const titleSpan = document.createElement("span");
  titleSpan.className = "collapse-title";
  titleSpan.textContent = title;
  titleWrap.append(chevron, titleSpan);

  const pill = document.createElement("span");
  pill.className = `summary-pill pill-${summaryVariant}`;
  if (summaryId) pill.id = summaryId;
  pill.textContent = summaryText;
  if (!summaryText) pill.classList.add("hidden");

  trigger.append(titleWrap, pill);

  const body = document.createElement("div");
  body.id = bodyId;
  body.className = "collapse-body";
  const inner = document.createElement("div");
  inner.className = "collapse-inner";
  if (contentEl) inner.appendChild(contentEl);
  body.appendChild(inner);

  if (!defaultOpen) wrapper.classList.add("is-collapsed");
  wrapper.append(trigger, body);

  return { wrapper, inner, pill };
}

export class MenuCollapseController {
  constructor({ storage = window.localStorage } = {}) {
    this.storage = storage;
    this.store = loadPersistedStore(storage);
    this.toggleHooks = new Map();
  }

  onToggle(id, callback) {
    if (!this.toggleHooks.has(id)) {
      this.toggleHooks.set(id, []);
    }
    this.toggleHooks.get(id).push(callback);
  }

  isOpen(id, defaultOpen = true) {
    if (id in this.store.panels) {
      return Boolean(this.store.panels[id]);
    }
    return defaultOpen;
  }

  setOpen(menuEl, open, { persist = true } = {}) {
    const id = menuEl.dataset.collapseId;
    const trigger = menuEl.querySelector(
      ":scope > .collapse-trigger, :scope > .collapse-header-row > .collapse-trigger"
    );
    menuEl.classList.toggle("is-collapsed", !open);
    if (trigger) trigger.setAttribute("aria-expanded", open ? "true" : "false");

    if (persist && id) {
      this.store.panels[id] = open;
      savePersistedStore(this.storage, this.store);
    }

    if (id && this.toggleHooks.has(id)) {
      for (const cb of this.toggleHooks.get(id)) cb(open, menuEl);
    }
  }

  registerContainer(root = document) {
    const menus = root.querySelectorAll("[data-collapse-id]");
    for (const menuEl of menus) {
      const id = menuEl.dataset.collapseId;
      const defaultOpen = menuEl.dataset.collapseDefault !== "closed";
      const open = this.isOpen(id, defaultOpen);
      this.setOpen(menuEl, open, { persist: false });

      if (menuEl.dataset.collapseBound === "1") continue;
      menuEl.dataset.collapseBound = "1";

      const trigger = menuEl.querySelector(
        ":scope > .collapse-trigger, :scope > .collapse-header-row > .collapse-trigger"
      );
      if (!trigger) continue;

      const body = menuEl.querySelector(":scope > .collapse-body");
      if (body && id) {
        if (!body.id) body.id = `collapse-body-${id}`;
        trigger.setAttribute("aria-controls", body.id);
      }

      // Ensure static HTML chevrons match the vector SVG used by dynamic sections
      const existingChevron = trigger.querySelector(".chevron");
      if (existingChevron && !existingChevron.querySelector("svg")) {
        existingChevron.innerHTML = CHEVRON_SVG;
      }

      trigger.addEventListener("click", () => {
        const nextOpen = menuEl.classList.contains("is-collapsed");
        this.setOpen(menuEl, nextOpen, { persist: true });
      });
    }
  }

  setSummary(pillOrCollapseId, text, variant = "neutral") {
    let pill = document.getElementById(pillOrCollapseId);
    if (!pill) {
      const menuEl = document.querySelector(`[data-collapse-id="${CSS.escape(pillOrCollapseId)}"]`);
      pill = menuEl?.querySelector(
        ":scope > .collapse-trigger > .summary-pill, :scope > .collapse-header-row > .collapse-trigger > .summary-pill"
      );
    }
    if (!pill) return;
    pill.textContent = text;
    pill.classList.toggle("hidden", !text);
    pill.classList.remove("pill-neutral", "pill-accent", "pill-warn", "pill-ok");
    pill.classList.add(`pill-${variant}`);
  }
}

export class SidebarController {
  constructor({
    workspaceEl,
    collapseLeftBtn,
    collapseRightBtn,
    expandLeftBtn,
    expandRightBtn,
    storage = window.localStorage,
    onLayoutChange = null,
  }) {
    this.workspaceEl = workspaceEl;
    this.collapseLeftBtn = collapseLeftBtn;
    this.collapseRightBtn = collapseRightBtn;
    this.expandLeftBtn = expandLeftBtn;
    this.expandRightBtn = expandRightBtn;
    this.storage = storage;
    this.onLayoutChange = onLayoutChange;
    this.store = loadPersistedStore(storage);
    this._resizeTimer = null;
  }

  init() {
    this.apply("left", this.store.sidebars.left, { persist: false, notify: false });
    this.apply("right", this.store.sidebars.right, { persist: false, notify: false });

    this.collapseLeftBtn?.addEventListener("click", () => this.apply("left", true));
    this.expandLeftBtn?.addEventListener("click", () => this.apply("left", false));
    this.collapseRightBtn?.addEventListener("click", () => this.apply("right", true));
    this.expandRightBtn?.addEventListener("click", () => this.apply("right", false));

    this.workspaceEl?.addEventListener("transitionend", (e) => {
      if (e.target === this.workspaceEl && e.propertyName === "grid-template-columns") {
        this.onLayoutChange?.();
      }
    });
  }

  apply(side, collapsed, { persist = true, notify = true } = {}) {
    if (!this.workspaceEl) return;
    if (side === "left") {
      this.workspaceEl.classList.toggle("left-collapsed", collapsed);
      this.expandLeftBtn?.classList.toggle("hidden", !collapsed);
      this.store.sidebars.left = collapsed;
    } else {
      this.workspaceEl.classList.toggle("right-collapsed", collapsed);
      this.expandRightBtn?.classList.toggle("hidden", !collapsed);
      this.store.sidebars.right = collapsed;
    }

    if (persist) {
      const current = loadPersistedStore(this.storage);
      current.sidebars = { ...this.store.sidebars };
      savePersistedStore(this.storage, current);
    }

    if (notify && this.onLayoutChange) {
      requestAnimationFrame(() => this.onLayoutChange());
      clearTimeout(this._resizeTimer);
      this._resizeTimer = setTimeout(() => this.onLayoutChange(), 240);
    }
  }
}
