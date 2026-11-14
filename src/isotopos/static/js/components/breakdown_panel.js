// Right Drawer: Ranked Earth Analogs list, Chart.js dimension chart & nested breakdown

import { state } from "../state.js";

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
    const item = document.createElement("div");
    item.className = `rank-item ${r.site.id === state.selectedSiteId ? "selected" : ""}`;
    const pct = (r.overall_score * 100).toFixed(1);
    const tag = r.site.site_type === "hotspot" ? (r.site.is_well_known ? "Baseline" : "Novel") : "H3 Res 4";
    item.innerHTML = `
      <div>
        <div class="rank-item-name">${r.site.name}</div>
        <div class="rank-item-sub">${r.site.region} • ${tag}</div>
      </div>
      <div class="score-pill">${pct}%</div>
    `;
    item.addEventListener("click", () => onSelectSite(r));
    listEl.appendChild(item);
  }
}

export function showBreakdown(result, { collapseCtrl, onSelectSite }) {
  state.selectedSiteId = result.site.id;
  if (state.map && state.map.getLayer("earth-h3-selected")) {
    state.map.setFilter("earth-h3-selected", ["==", ["get", "id"], result.site.id]);
  }

  document.getElementById("breakdown-card").classList.remove("hidden");
  document.getElementById("detail-name").textContent = result.site.name;
  document.getElementById("detail-meta").textContent =
    `${result.site.region} (${result.site.lat.toFixed(2)}°, ${result.site.lon.toFixed(2)}°)`;
  document.getElementById("detail-score-badge").textContent = `${(result.overall_score * 100).toFixed(1)}%`;
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
    div.innerHTML = `<strong>${c.title}</strong><span>${c.explanation}</span>`;
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
    tr.innerHTML = `
      <td>${comp.label}<br/><small>${comp.unit}</small></td>
      <td>${comp.earth_value}</td>
      <td>${comp.target_value}</td>
      <td>${comp.weight === 0 ? "N/A" : Math.round(comp.similarity * 100) + "%"}</td>
      <td>
        <a href="${pSpec.earth_provenance.url}" target="_blank" rel="noopener">${pSpec.earth_provenance.agency_mission}</a> /
        <a href="${pProv.url}" target="_blank" rel="noopener">${pProv.agency_mission}</a>
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
