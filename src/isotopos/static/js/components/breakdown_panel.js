// Right Drawer: Unified Ranked Earth Analogs list, dual visual preview, Chart.js & DR-3 table

import { state } from "../state.js";
import { escapeHtml } from "../ui/dom.js";
import { highlightSelectedSiteOnMap } from "./globe_map.js";

let photoReqSeq = 0;
const wikiGeoPhotoCache = {};
let chartResizeObserverBound = false;

export function resizeDimensionChart() {
  state.chart?.resize();
}

function ensureChartResizeObserver() {
  if (chartResizeObserverBound || typeof ResizeObserver === "undefined") return;
  const wrap = document.querySelector(".chart-wrap");
  if (!wrap) return;
  chartResizeObserverBound = true;
  let rafId = 0;
  new ResizeObserver(() => {
    if (rafId) return;
    rafId = requestAnimationFrame(() => {
      rafId = 0;
      resizeDimensionChart();
    });
  }).observe(wrap);
}

export function getActiveTabPool(rankResponse, tab = state.activeTab) {
  if (!rankResponse) return [];
  const h3 = rankResponse.top_h3_results || [];
  const hs = rankResponse.hotspot_results || [];
  if (tab === "hotspots") return hs;
  if (tab === "h3") return h3;
  return [...h3, ...hs].sort((a, b) => b.overall_score - a.overall_score).slice(0, 25);
}

function computeEsriOverheadTile(lat, lon, zoom = 11) {
  if (Math.abs(lat) > 85.0) return null;
  const n = 2 ** zoom;
  const xFloat = ((lon + 180) / 360) * n;
  const latRad = (lat * Math.PI) / 180;
  const yFloat = ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n;
  const x = Math.max(0, Math.min(n - 1, Math.floor(xFloat)));
  const y = Math.max(0, Math.min(n - 1, Math.floor(yFloat)));
  return {
    url: `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${zoom}/${y}/${x}`,
    pctX: Math.round((xFloat - x) * 100),
    pctY: Math.round((yFloat - y) * 100),
  };
}

async function resolveWikiGeoPhoto(lat, lon) {
  const key = `${lat.toFixed(2)},${lon.toFixed(2)}`;
  if (key in wikiGeoPhotoCache) return wikiGeoPhotoCache[key];
  try {
    const url =
      `https://en.wikipedia.org/w/api.php?action=query&generator=geosearch` +
      `&ggscoord=${encodeURIComponent(lat)}|${encodeURIComponent(lon)}` +
      `&ggsradius=10000&ggslimit=1&prop=pageimages&piprop=thumbnail&pithumbsize=420&format=json&origin=*`;
    const resp = await fetch(url);
    if (!resp.ok) {
      wikiGeoPhotoCache[key] = null;
      return null;
    }
    const data = await resp.json();
    const pages = Object.values(data?.query?.pages || {});
    const page = pages[0];
    const thumb = page?.thumbnail?.source || null;
    const result = thumb ? { url: thumb, title: page.title || "Wikipedia" } : null;
    wikiGeoPhotoCache[key] = result;
    return result;
  } catch {
    wikiGeoPhotoCache[key] = null;
    return null;
  }
}

function updateVisualPreviews(site) {
  const seq = ++photoReqSeq;
  const photoImg = document.getElementById("detail-photo-img");
  const photoFallback = document.getElementById("detail-photo-fallback");
  const photoCaption = document.getElementById("detail-photo-caption");

  const satImg = document.getElementById("detail-sat-img");
  const satCrosshair = document.getElementById("detail-sat-crosshair");
  const satFallback = document.getElementById("detail-sat-fallback");
  const satCaption = document.getElementById("detail-sat-caption");

  // 1. Overhead satellite preview (Esri World Imagery z11)
  const tile = computeEsriOverheadTile(site.lat, site.lon, 11);
  if (satImg && satCrosshair && satFallback && satCaption) {
    satImg.classList.add("hidden");
    satCrosshair.classList.add("hidden");
    satFallback.classList.remove("hidden");
    if (tile) {
      satFallback.textContent = "Loading overhead imagery…";
      satCaption.textContent = `Esri Imagery z11 · ${site.lat.toFixed(2)}°, ${site.lon.toFixed(2)}°`;
      satImg.onload = () => {
        if (seq !== photoReqSeq) return;
        satImg.classList.remove("hidden");
        satCrosshair.classList.remove("hidden");
        satCrosshair.style.left = `${tile.pctX}%`;
        satCrosshair.style.top = `${tile.pctY}%`;
        satFallback.classList.add("hidden");
      };
      satImg.onerror = () => {
        if (seq !== photoReqSeq) return;
        satImg.classList.add("hidden");
        satCrosshair.classList.add("hidden");
        satFallback.classList.remove("hidden");
        satFallback.textContent = "Overhead tile unavailable offline";
      };
      satImg.src = tile.url;
    } else {
      satFallback.textContent = `Polar region (${site.lat.toFixed(1)}°) outside Web Mercator tile bounds`;
      satCaption.textContent = "Polar Coordinates";
    }
  }

  // 2. Site Field Photo (Curated Wikimedia or Wikipedia GeoSearch for H3 cells)
  if (!photoImg || !photoFallback || !photoCaption) return;
  const fallbackSummary =
    `${site.country || site.region}\n` +
    `${Math.round(site.parameters?.elevation_m ?? 0)} m elev · ` +
    `${(site.parameters?.mean_temp_c ?? 0).toFixed(1)} °C`;

  photoImg.classList.add("hidden");
  photoFallback.classList.remove("hidden");
  photoFallback.textContent = fallbackSummary;

  if (site.photo_url) {
    photoCaption.textContent = site.photo_attribution || "Wikimedia Commons";
    photoImg.onload = () => {
      if (seq !== photoReqSeq) return;
      photoImg.classList.remove("hidden");
      photoFallback.classList.add("hidden");
    };
    photoImg.onerror = () => {
      if (seq !== photoReqSeq) return;
      photoImg.classList.add("hidden");
      photoFallback.classList.remove("hidden");
    };
    photoImg.src = site.photo_url;
  } else {
    photoCaption.textContent = "Searching nearby Wikipedia imagery…";
    resolveWikiGeoPhoto(site.lat, site.lon).then((wiki) => {
      if (seq !== photoReqSeq) return;
      if (wiki?.url) {
        photoCaption.textContent = `Wikipedia nearby: ${wiki.title}`;
        photoImg.onload = () => {
          if (seq !== photoReqSeq) return;
          photoImg.classList.remove("hidden");
          photoFallback.classList.add("hidden");
        };
        photoImg.onerror = () => {
          if (seq !== photoReqSeq) return;
          photoImg.classList.add("hidden");
          photoFallback.classList.remove("hidden");
          photoCaption.textContent = "Regional Physical Profile";
        };
        photoImg.src = wiki.url;
      } else {
        photoCaption.textContent = "Regional Physical Profile";
      }
    });
  }
}

export function renderRankedList({ onSelectSite }) {
  const listEl = document.getElementById("ranked-list");
  if (!listEl || !state.lastRankResponse) return;
  listEl.innerHTML = "";
  const results = getActiveTabPool(state.lastRankResponse, state.activeTab);

  if (!results.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No Earth analog sites match the current filters.";
    listEl.appendChild(empty);
    return;
  }

  results.forEach((r, idx) => {
    const isSelected = r.site.id === state.selectedSiteId;
    const item = document.createElement("button");
    item.type = "button";
    item.className = `rank-item ${isSelected ? "selected" : ""}`;
    item.setAttribute("aria-pressed", isSelected ? "true" : "false");
    const pct = (r.overall_score * 100).toFixed(1);
    const isHotspot = r.site.site_type === "hotspot";
    const typeBadge = isHotspot
      ? r.site.is_well_known
        ? "Baseline Site"
        : "Named Site"
      : "H3 Region";
    const place =
      r.site.country && r.site.country !== r.site.region
        ? `${r.site.country} · ${r.site.region}`
        : r.site.region;
    const rankNum = state.activeTab === "all" ? idx + 1 : r.rank;
    item.innerHTML = `
      <span class="rank-item-info">
        <span class="rank-item-name">#${rankNum} ${escapeHtml(r.site.name)}</span>
        <span class="rank-item-sub">
          <span class="rank-type-badge ${isHotspot ? "hotspot" : ""}">${escapeHtml(typeBadge)}</span>${escapeHtml(place)}
        </span>
      </span>
      <span class="score-pill mono-num">${escapeHtml(pct)}%</span>
    `;
    item.addEventListener("click", () => onSelectSite(r));
    listEl.appendChild(item);
  });
}

export function showBreakdown(result, { collapseCtrl, onSelectSite }) {
  state.selectedSiteId = result.site.id;
  highlightSelectedSiteOnMap(result.site.id, [result.site.lon, result.site.lat]);

  document.getElementById("breakdown-card").classList.remove("hidden");
  document.getElementById("detail-name").textContent = result.site.name;
  const locText =
    result.site.country && result.site.country !== result.site.region
      ? `${result.site.country} · ${result.site.region}`
      : result.site.region;
  document.getElementById("detail-meta").textContent =
    `${locText} (${result.site.lat.toFixed(2)}°, ${result.site.lon.toFixed(2)}°)`;
  document.getElementById("detail-score-badge").textContent =
    `${(result.overall_score * 100).toFixed(1)}%`;
  document.getElementById("detail-notes").textContent = result.site.notes || "";

  const typeBadge = document.getElementById("detail-type-badge");
  if (typeBadge) {
    if (result.site.site_type === "hotspot") {
      typeBadge.textContent = result.site.is_well_known ? "Well-Known Baseline" : "Novel Analog Hotspot";
      typeBadge.className = `badge ${result.site.is_well_known ? "badge-warn" : "badge-neutral"}`;
    } else {
      typeBadge.textContent = "H3 Res 4 Grid Cell";
      typeBadge.className = "badge badge-neutral";
    }
  }

  const interpParams = result.site.interpolated_parameters || [];
  const interpBadge = document.getElementById("detail-interp-badge");
  if (interpBadge) {
    if (interpParams.length > 0) {
      interpBadge.textContent = `Gap-Filled: ${interpParams.length} param${interpParams.length > 1 ? "s" : ""}`;
      interpBadge.title = `Spatially interpolated where satellite/station tracks had gaps: ${interpParams.join(", ")}`;
      interpBadge.className = "badge badge-warn";
    } else {
      interpBadge.textContent = "Direct Open Grid";
      interpBadge.title = "All site parameters observed directly from open global grids";
      interpBadge.className = "badge badge-neutral";
    }
  }

  updateVisualPreviews(result.site);

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

  if (state.chart) {
    state.chart.data.labels = labels;
    state.chart.data.datasets[0].data = values;
    state.chart.data.datasets[0].backgroundColor = colors;
    state.chart.update("none");
  } else {
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
    ensureChartResizeObserver();
  }

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
  const interpSet = new Set(interpParams);
  const tbody = document.getElementById("detail-comparison-body");
  tbody.innerHTML = "";
  for (const comp of result.parameter_comparisons) {
    const pSpec = state.metadata.parameters.find((p) => p.id === comp.parameter_id);
    const pProv = state.body === "moon" ? pSpec.moon_provenance : pSpec.mars_provenance;
    const tr = document.createElement("tr");
    const simText = comp.weight === 0 ? "N/A" : `${Math.round(comp.similarity * 100)}%`;
    const gapNote = interpSet.has(comp.parameter_id) ? '<br/><small class="gap-note">Gap-filled</small>' : "";
    tr.innerHTML = `
      <td>${escapeHtml(comp.label)}<br/><small>${escapeHtml(comp.unit)}</small></td>
      <td class="mono-num">${escapeHtml(comp.earth_value)}${gapNote}</td>
      <td class="mono-num">${escapeHtml(comp.target_value)}</td>
      <td class="mono-num">${escapeHtml(simText)}</td>
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
