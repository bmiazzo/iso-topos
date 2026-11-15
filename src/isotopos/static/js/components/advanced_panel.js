// Advanced Evaluation controls: dynamic Level-3 Dimension weight menus, filters & export

import { exportAnalogsBlob } from "../api.js";
import { state } from "../state.js";
import { createCollapsibleSection } from "../ui/collapsible.js";
import { announcePolite, escapeHtml } from "../ui/dom.js";
import { updateTargetBadge } from "./target_panel.js";

const FILTER_INPUT_IDS = ["flt-max-slope", "flt-min-temp", "flt-max-temp", "flt-min-aridity"];
const TEMP_ERROR_MSG = "Minimum temperature cannot exceed maximum temperature.";

function setTemperatureValidation(minTempEl, maxTempEl, inverted) {
  const wasInvalid = minTempEl?.getAttribute("aria-invalid") === "true";
  for (const el of [minTempEl, maxTempEl]) {
    if (!el) continue;
    el.classList.toggle("input-invalid", inverted);
    if (inverted) {
      el.setAttribute("aria-invalid", "true");
      el.setAttribute("aria-describedby", "filter-validation-error");
    } else {
      el.removeAttribute("aria-invalid");
      el.removeAttribute("aria-describedby");
    }
  }
  const errEl = document.getElementById("filter-validation-error");
  if (errEl) {
    errEl.textContent = inverted ? TEMP_ERROR_MSG : "";
    errEl.classList.toggle("hidden", !inverted);
  }
  if (inverted && !wasInvalid) {
    announcePolite(TEMP_ERROR_MSG);
  }
}

export function buildActiveFilters() {
  const filters = [];
  const maxSlope = parseFloat(document.getElementById("flt-max-slope")?.value);
  if (!Number.isNaN(maxSlope)) filters.push({ parameter_id: "slope_deg", max_value: maxSlope });

  const minTempEl = document.getElementById("flt-min-temp");
  const maxTempEl = document.getElementById("flt-max-temp");
  const minTemp = parseFloat(minTempEl?.value);
  const maxTemp = parseFloat(maxTempEl?.value);
  const invertedTemp = !Number.isNaN(minTemp) && !Number.isNaN(maxTemp) && minTemp > maxTemp;
  setTemperatureValidation(minTempEl, maxTempEl, invertedTemp);

  if (!invertedTemp && (!Number.isNaN(minTemp) || !Number.isNaN(maxTemp))) {
    filters.push({
      parameter_id: "mean_temp_c",
      min_value: Number.isNaN(minTemp) ? null : minTemp,
      max_value: Number.isNaN(maxTemp) ? null : maxTemp,
    });
  }

  const minAridity = parseFloat(document.getElementById("flt-min-aridity")?.value);
  if (!Number.isNaN(minAridity)) {
    filters.push({ parameter_id: "aridity_dryness_index", min_value: minAridity });
  }
  return filters;
}

export function buildAdvancedControls({ collapseCtrl, onScheduleRank, onSyncSummaries }) {
  const container = document.getElementById("parameter-weights-container");
  if (!container || !state.metadata) return;
  container.innerHTML = "";

  for (const dim of state.metadata.dimensions) {
    const dimContent = document.createElement("div");
    const dimParams = state.metadata.parameters.filter((p) => p.dimension_id === dim.id);

    for (const p of dimParams) {
      const defaultPct = Math.round((p.default_weight ?? 0.8) * 100);
      const isEnabled = defaultPct > 0;
      const row = document.createElement("div");
      row.className = "param-row";
      row.innerHTML = `
        <div class="param-row-top">
          <span title="${escapeHtml(p.description)}">${escapeHtml(p.label)} <small>(${escapeHtml(p.unit)})</small></span>
          <label><input type="checkbox" id="chk-en-${escapeHtml(p.id)}" ${isEnabled ? "checked" : ""} /> Active</label>
        </div>
        <div class="param-row-controls">
          <input type="number" class="param-override-input" id="val-${escapeHtml(p.id)}" step="any" title="Override target value" />
          <input type="range" id="wt-${escapeHtml(p.id)}" min="0" max="100" step="5" value="${defaultPct}" />
          <span id="wt-lbl-${escapeHtml(p.id)}">${defaultPct}%</span>
        </div>
      `;
      dimContent.appendChild(row);

      const valInput = row.querySelector(`#val-${CSS.escape(p.id)}`);
      const wtSlider = row.querySelector(`#wt-${CSS.escape(p.id)}`);
      const wtLabel = row.querySelector(`#wt-lbl-${CSS.escape(p.id)}`);
      const chkEnable = row.querySelector(`#chk-en-${CSS.escape(p.id)}`);

      const onOverrideEdit = () => {
        if (!state.target) return;
        const parsed = parseFloat(valInput.value);
        if (Number.isNaN(parsed)) return;
        state.target.parameters[p.id] = parsed;
        state.targetCustomized = true;
        state.activePresetId = null;
        const presetSel = document.getElementById("preset-select");
        if (presetSel) presetSel.value = "__custom__";
        updateTargetBadge();
        onSyncSummaries?.();
        onScheduleRank();
      };
      valInput.addEventListener("input", onOverrideEdit);
      valInput.addEventListener("change", onOverrideEdit);

      wtSlider.addEventListener("input", () => {
        const w = parseInt(wtSlider.value, 10) / 100.0;
        state.weights[p.id] = w;
        wtLabel.textContent = `${wtSlider.value}%`;
        chkEnable.checked = w > 0;
        onSyncSummaries?.();
        onScheduleRank();
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
        onSyncSummaries?.();
        onScheduleRank();
      });
    }

    const { wrapper } = createCollapsibleSection({
      id: `dim-${dim.id}`,
      title: dim.name,
      level: 3,
      defaultOpen: false,
      summaryId: `summary-dim-${dim.id}`,
      summaryText: `${dimParams.length}/${dimParams.length}`,
      summaryVariant: "ok",
      contentEl: dimContent,
    });
    container.appendChild(wrapper);
  }

  collapseCtrl.registerContainer(container);
}

export async function exportAnalogs(format) {
  if (!state.target) return;
  const blob = await exportAnalogsBlob(format, {
    target: state.target,
    weights: state.weights,
    mode: state.scoringMode,
    filters: buildActiveFilters(),
    exclude_well_known: state.excludeWellKnown,
    top_k: 25,
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `isotopos_analogs.${format}`;
  a.click();
  URL.revokeObjectURL(url);
}

export function bindAdvancedEvents({ onRank, onScheduleRank, onSyncSummaries }) {
  document.getElementById("scoring-mode-select")?.addEventListener("change", (e) => {
    state.scoringMode = e.target.value;
    onSyncSummaries?.();
    onRank();
  });

  for (const id of FILTER_INPUT_IDS) {
    const el = document.getElementById(id);
    if (!el) continue;
    const handler = () => {
      onSyncSummaries?.();
      onScheduleRank();
    };
    el.addEventListener("input", handler);
    el.addEventListener("change", handler);
  }

  document.getElementById("btn-reset-filters")?.addEventListener("click", () => {
    for (const id of FILTER_INPUT_IDS) {
      const el = document.getElementById(id);
      if (el) {
        el.value = "";
        el.classList.remove("input-invalid");
      }
    }
    setTemperatureValidation(
      document.getElementById("flt-min-temp"),
      document.getElementById("flt-max-temp"),
      false
    );
    onSyncSummaries?.();
    onRank();
  });

  document.getElementById("btn-export-csv")?.addEventListener("click", () => exportAnalogs("csv"));
  document.getElementById("btn-export-json")?.addEventListener("click", () => exportAnalogs("json"));
}
