// Right Drawer: Ranked Earth Analogs list, Chart.js dimension chart & nested breakdown

import { state } from "../state.js";
import { escapeHtml } from "../ui/dom.js";
import { highlightSelectedSiteOnMap } from "./globe_map.js";

export function resizeDimensionChart() {
  state.chart?.resize();
}

export function renderRankedList({ onSelectSite }) {
  const listEl = document.getElementById("ranked-list");
  if (!listEl || !state.lastRankResponse) return;
  listEl.innerHTML = "";
  const results =
    state.activeTab === "hotspots"
      ? state.lastRankResponse.hotspot_results
      : state.lastRankResponse.top_h3_results;

  if (!results.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No Earth analog sites match the current filters.";
    listEl.appendChild(empty);
    return;
  }

  for (const r of results) {
    const isSelected = r.site.id === state.selectedSiteId;
    const item = document.createElement("button");
    item.type = "button";
    item.className = `rank-item ${isSelected ? "selected" : ""}`;
    item.setAttribute("aria-pressed", isSelected ? "true" : "false");
    const pct = (r.overall_score * 100).toFixed(1);
    const tag =
      r.site.site_type === "hotspot" ? (r.site.is_well_known ? "Baseline" : "Novel") : "H3 Res 4";
    item.innerHTML = `
      <div>
        <div class="rank-item-name">${escapeHtml(r.site.name)}</div>
        <div class="rank-item-sub">${escapeHtml(r.site.region)} • ${escapeHtml(tag)}</div>
      </div>
      <div class="score-pill">${escapeHtml(pct)}%</div>
    `;
    item.addEventListener("click", () => onSelectSite(r));
    listEl.appendChild(item);
  }
}

export function showBreakdown(result, { collapseCtrl, onSelectSite }) {
  state.selectedSiteId = result.site.id;
  highlightSelectedSiteOnMap(result.site.id);

  document.getElementById("breakdown-card").classList.remove("hidden");
  document.getElementById("detail-name").textContent = result.site.name;
  document.getElementById("detail-meta").textContent =
    `${result.site.region} (${result.site.lat.toFixed(2)}°, ${result.site.lon.toFixed(2)}°)`;
  document.getElementById("detail-score-badge").textContent =
    `${(result.overall_score * 100).toFixed(1)}%`;
  document.getElementById("detail-notes").textContent = result.site.notes || "";

  const labels = result.dimension_breakdowns.map((d) =>
    d.sub_score === null ? `${d.dimension_name} (N/A)` : d.dimension_name
  );
  const values = result.dimension_breakdowns.map((d) =>
    d.sub_score === null ? 0 : Math.round(d.sub_score * 100)
  );
  const colors = result.dimension_breakdowns.map((d) =>
    d.status === "N/A"
      ? "#475569"
      : d.status === "strong"
      ? "#2dd4bf"
      : d.status === "moderate"
      ? "#38bdf8"
      : "#f59e0b"
  );

  if (state.chart) state.chart.destroy();
  const ctx = document.getElementById("dimension-chart").getContext("2d");
  state.chart = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{ label: "Dimension Similarity (%)", data: values, backgroundColor: colors }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        x: { min: 0, max: 100, ticks: { color: "#93a4c3" }, grid: { color: "#27324a" } },
        y: { ticks: { color: "#e6edf7", font: { size: 10 } }, grid: { display: false } },
      },
      plugins: { legend: { display: false } },
    },
  });

  // Relevance
  const relEl = document.getElementById("detail-relevance");
  relEl.innerHTML = "";
  for (const item of result.exploration_relevance) {
    const li = document.createElement("li");
    li.textContent = item;
    relEl.appendChild(li);
  }
  collapseCtrl?.setSummary(
    "summary-relevance",
    `${result.exploration_relevance.length} tags`,
    result.exploration_relevance.length ? "accent" : "neutral"
  );

  // Earth-Limit Caveats
  const cavEl = document.getElementById("detail-caveats");
  cavEl.innerHTML = "";
  for (const c of result.earth_limit_caveats) {
    const div = document.createElement("div");
    div.className = "caveat-card";
    const strong = document.createElement("strong");
    strong.textContent = c.title;
    const span = document.createElement("span");
    span.textContent = c.explanation;
    div.append(strong, span);
    cavEl.appendChild(div);
  }
  collapseCtrl?.setSummary(
    "summary-caveats",
    `${result.earth_limit_caveats.length} caveats`,
    result.earth_limit_caveats.length ? "warn" : "neutral"
  );

  // Provenance & Unit-Level Comparison Table
  const tbody = document.getElementById("detail-comparison-body");
  tbody.innerHTML = "";
  for (const comp of result.parameter_comparisons) {
    const pSpec = state.metadata.parameters.find((p) => p.id === comp.parameter_id);
    const pProv = state.body === "moon" ? pSpec.moon_provenance : pSpec.mars_provenance;
    const tr = document.createElement("tr");
    const simText = comp.weight === 0 ? "N/A" : `${Math.round(comp.similarity * 100)}%`;
    tr.innerHTML = `
      <td>${escapeHtml(comp.label)}<br/><small>${escapeHtml(comp.unit)}</small></td>
      <td>${escapeHtml(comp.earth_value)}</td>
      <td>${escapeHtml(comp.target_value)}</td>
      <td>${escapeHtml(simText)}</td>
      <td>
        <a href="${escapeHtml(pSpec.earth_provenance.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(pSpec.earth_provenance.agency_mission)}</a> /
        <a href="${escapeHtml(pProv.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(pProv.agency_mission)}</a>
      </td>
    `;
    tbody.appendChild(tr);
  }
  collapseCtrl?.setSummary(
    "summary-provenance",
    `${result.parameter_comparisons.length} params`,
    "neutral"
  );

  renderRankedList({ onSelectSite });
}
