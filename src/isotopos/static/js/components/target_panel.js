// Target Selection panel: Preset dropdown, Moon/Mars body switching & target control sync

import { state } from "../state.js";
import { setButtonPressed } from "../ui/dom.js";
import { bindPlanetaryPickerEvents, drawPlanetaryPicker } from "./planetary_picker.js";

export function populatePresetDropdown() {
  const sel = document.getElementById("preset-select");
  if (!sel || !state.metadata) return;
  sel.innerHTML = "";
  const bodyPresets = state.metadata.presets.filter((p) => p.body === state.body);
  for (const p of bodyPresets) {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = `${p.name} (${p.lat.toFixed(1)}°, ${p.lon.toFixed(1)}°E)`;
    sel.appendChild(opt);
  }
  const customOpt = document.createElement("option");
  customOpt.value = "__custom__";
  customOpt.textContent = "— Custom Planetary Coordinate / Override —";
  customOpt.disabled = true;
  sel.appendChild(customOpt);
}

export function updateTargetBadge() {
  const badge = document.getElementById("extrapolation-badge");
  if (!badge || !state.target) return;
  if (state.target.is_extrapolated) {
    badge.textContent = "Extrapolated Target";
    badge.className = "badge badge-warn";
  } else if (state.targetCustomized) {
    badge.textContent = "Custom Override";
    badge.className = "badge badge-warn";
  } else {
    badge.textContent = "Preset Exact";
    badge.className = "badge badge-neutral";
  }
}

export function syncControlsFromTarget({ onSyncSummaries } = {}) {
  if (!state.target || !state.metadata) return;
  const latInput = document.getElementById("input-lat");
  const lonInput = document.getElementById("input-lon");
  if (latInput) latInput.value = state.target.lat.toFixed(2);
  if (lonInput) lonInput.value = state.target.lon.toFixed(2);

  updateTargetBadge();

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
  onSyncSummaries?.();
}

export function bindTargetPanelEvents({ onSelectPreset, onExtractCoordinate }) {
  const moonBtn = document.getElementById("btn-body-moon");
  const marsBtn = document.getElementById("btn-body-mars");

  const switchBody = async (nextBody) => {
    state.body = nextBody;
    setButtonPressed(moonBtn, nextBody === "moon");
    setButtonPressed(marsBtn, nextBody === "mars");
    populatePresetDropdown();
    const first = state.metadata?.presets.find((p) => p.body === nextBody);
    if (first) await onSelectPreset(first.id);
  };

  moonBtn?.addEventListener("click", () => switchBody("moon"));
  marsBtn?.addEventListener("click", () => switchBody("mars"));

  document.getElementById("preset-select")?.addEventListener("change", (e) => {
    onSelectPreset(e.target.value);
  });

  bindPlanetaryPickerEvents({
    onSelectPreset,
    onExtractCoordinate,
  });
}
