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
