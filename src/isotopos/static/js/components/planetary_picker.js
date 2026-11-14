// 2D Moon & Mars clickable planetary coordinate picker

import { state } from "../state.js";

export function drawPlanetaryPicker() {
  const canvas = document.getElementById("planetary-picker-canvas");
  if (!canvas || !state.metadata) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;

  ctx.fillStyle = state.body === "moon" ? "#1e2430" : "#3a1e16";
  ctx.fillRect(0, 0, w, h);

  ctx.fillStyle = state.body === "moon" ? "rgba(15, 18, 26, 0.45)" : "rgba(95, 42, 24, 0.35)";
  for (let i = 0; i < 18; i++) {
    const rx = ((i * 73) % 280) + 10;
    const ry = ((i * 41) % 120) + 15;
    ctx.beginPath();
    ctx.arc(rx, ry, 10 + (i % 14), 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  ctx.lineWidth = 1;
  for (let gx = 0; gx <= w; gx += w / 6) {
    ctx.beginPath();
    ctx.moveTo(gx, 0);
    ctx.lineTo(gx, h);
    ctx.stroke();
  }
  for (let gy = 0; gy <= h; gy += h / 4) {
    ctx.beginPath();
    ctx.moveTo(0, gy);
    ctx.lineTo(w, gy);
    ctx.stroke();
  }

  if (state.showMissions) {
    ctx.font = "9px Inter, sans-serif";
    ctx.textBaseline = "middle";
    for (const p of state.metadata.presets.filter((pr) => pr.body === state.body)) {
      const lonNorm = ((p.lon % 360) + 360) % 360;
      const x = (lonNorm / 360) * w;
      const y = ((90 - p.lat) / 180) * h;
      const isSelected = p.id === state.activePresetId;

      ctx.fillStyle = isSelected ? "#fbbf24" : "#cbd5e1";
      ctx.beginPath();
      ctx.arc(x, y, isSelected ? 4 : 3, 0, Math.PI * 2);
      ctx.fill();

      const shortName = p.name.split(" ")[0];
      const labelX = x > w - 58 ? x - 6 : x + 6;
      ctx.textAlign = x > w - 58 ? "right" : "left";
      ctx.fillStyle = isSelected ? "#fde68a" : "rgba(226, 232, 240, 0.85)";
      ctx.fillText(shortName, labelX, Math.max(8, Math.min(h - 8, y)));
    }
  }

  if (state.target) {
    const lonNorm = ((state.target.lon % 360) + 360) % 360;
    const x = (lonNorm / 360) * w;
    const y = ((90 - state.target.lat) / 180) * h;
    ctx.strokeStyle = "#38bdf8";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(x, y, 6, 0, Math.PI * 2);
    ctx.stroke();
  }
}

export function bindPlanetaryPickerEvents({ onSelectPreset, onExtractCoordinate }) {
  document.getElementById("chk-show-missions")?.addEventListener("change", (e) => {
    state.showMissions = e.target.checked;
    drawPlanetaryPicker();
  });

  document.getElementById("btn-extract-coord")?.addEventListener("click", () => {
    const lat = parseFloat(document.getElementById("input-lat").value);
    const lon = parseFloat(document.getElementById("input-lon").value);
    if (!Number.isNaN(lat) && !Number.isNaN(lon)) {
      onExtractCoordinate(lat, lon);
    }
  });

  document.getElementById("planetary-picker-canvas")?.addEventListener("click", (e) => {
    const canvas = e.target;
    const rect = canvas.getBoundingClientRect();
    const clickX = ((e.clientX - rect.left) / rect.width) * canvas.width;
    const clickY = ((e.clientY - rect.top) / rect.height) * canvas.height;

    if (state.showMissions) {
      let nearest = null;
      let nearestDist = 9.0;
      for (const p of state.metadata.presets.filter((pr) => pr.body === state.body)) {
        const lonNorm = ((p.lon % 360) + 360) % 360;
        const px = (lonNorm / 360) * canvas.width;
        const py = ((90 - p.lat) / 180) * canvas.height;
        const d = Math.hypot(clickX - px, clickY - py);
        if (d < nearestDist) {
          nearestDist = d;
          nearest = p;
        }
      }
      if (nearest) {
        onSelectPreset(nearest.id);
        return;
      }
    }

    const lat = 90.0 - (clickY / canvas.height) * 180.0;
    const lon = (clickX / canvas.width) * 360.0;
    onExtractCoordinate(lat, lon);
  });
}
