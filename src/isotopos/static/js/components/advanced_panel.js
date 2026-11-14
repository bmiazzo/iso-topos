// Advanced Evaluation controls: dynamic Level-3 Dimension weight menus, filters & export

import { exportAnalogsBlob } from "../api.js";
import { state } from "../state.js";
import { createCollapsibleSection } from "../ui/collapsible.js";

const FILTER_INPUT_IDS = ["flt-max-slope", "flt-min-temp", "flt-max-temp", "flt-min-aridity"];

export function buildActiveFilters() {
  const filters = [];
  const maxSlope = parseFloat(document.getElementById("flt-max-slope")?.value);
  if (!Number.isNaN(maxSlope)) filters.push({ parameter_id: "slope_deg", max_value: maxSlope });

  const minTemp = parseFloat(document.getElementById("flt-min-temp")?.value);
  const maxTemp = parseFloat(document.getElementById("flt-max-temp")?.value);
  if (!Number.isNaN(minTemp) || !Number.isNaN(maxTemp)) {
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
  if (!container) return;
  container.innerHTML = "";

  for (const dim of state.metadata.dimensions) {
    const dimContent = document.createElement("div");
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
      dimContent.appendChild(row);

      const valInput = row.querySelector(`#val-${p.id}`);
      const wtSlider = row.querySelector(`#wt-${p.id}`);
      const wtLabel = row.querySelector(`#wt-lbl-${p.id}`);
      const chkEnable = row.querySelector(`#chk-en-${p.id}`);

      const onOverrideEdit = () => {
        if (!state.target) return;
        const parsed = parseFloat(valInput.value);
        if (Number.isNaN(parsed)) return;
        state.target.parameters[p.id] = parsed;
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
      if (el) el.value = "";
    }
    onSyncSummaries?.();
    onRank();
  });

  document.getElementById("btn-export-csv")?.addEventListener("click", () => exportAnalogs("csv"));
  document.getElementById("btn-export-json")?.addEventListener("click", () => exportAnalogs("json"));
}
