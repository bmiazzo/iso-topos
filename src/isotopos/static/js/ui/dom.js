// DOM safety and accessibility helpers

const HTML_ESCAPES = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => HTML_ESCAPES[ch]);
}

export function setButtonPressed(buttonEl, pressed) {
  if (!buttonEl) return;
  buttonEl.classList.toggle("active", Boolean(pressed));
  buttonEl.setAttribute("aria-pressed", pressed ? "true" : "false");
}

export function setSpinButtonState(buttonEl, enabled) {
  if (!buttonEl) return;
  const active = Boolean(enabled);
  buttonEl.textContent = active ? "Auto-Spin: ON" : "Auto-Spin: OFF";
  buttonEl.setAttribute("aria-pressed", active ? "true" : "false");
}

export function prefersReducedMotion() {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;
}

export function announcePolite(message) {
  const el = document.getElementById("a11y-announcer");
  if (!el) return;
  el.textContent = "";
  if (!message) return;
  requestAnimationFrame(() => {
    el.textContent = message;
  });
}
