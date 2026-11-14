// Thin REST API client isolating all backend HTTP calls

async function fetchJson(url, options) {
  const resp = await fetch(url, options);
  const data = await resp.json();
  if (!resp.ok) {
    throw new Error(data?.detail || `HTTP ${resp.status}`);
  }
  return data;
}

export function fetchMetadata() {
  return fetchJson("/api/v1/metadata");
}

export function fetchEarthGrid() {
  return fetchJson("/api/v1/earth-grid");
}

export async function fetchRawParameter(paramId) {
  const data = await fetchJson(`/api/v1/earth-grid/parameter/${encodeURIComponent(paramId)}`);
  return data.values || {};
}

export function extractTarget(payload) {
  return fetchJson("/api/v1/target/extract", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function rankAnalogs(payload) {
  return fetchJson("/api/v1/rank", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export async function inspectSite(siteId, payload) {
  const resp = await fetch(`/api/v1/site/${encodeURIComponent(siteId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) return null;
  return resp.json();
}

export function evaluateMissionWeightsApi(missionDescription) {
  return fetchJson("/api/v1/weights/evaluate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mission_description: missionDescription }),
  });
}

export async function exportAnalogsBlob(format, payload) {
  const resp = await fetch(`/api/v1/export?format=${encodeURIComponent(format)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) {
    let detail = `Export failed with HTTP ${resp.status}`;
    try {
      const errData = await resp.json();
      if (errData?.detail) detail = errData.detail;
    } catch {
      // Ignore non-JSON error body
    }
    throw new Error(detail);
  }
  return resp.blob();
}
