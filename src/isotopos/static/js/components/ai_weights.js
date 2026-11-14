// AI Mission Weight Evaluator component

import { evaluateMissionWeightsApi } from "../api.js";
import { state } from "../state.js";

export async function evaluateMissionWeights({ onWeightsApplied, onSyncSummaries }) {
  const input = document.getElementById("mission-description");
  const btn = document.getElementById("btn-evaluate-weights");
  const statusEl = document.getElementById("weight-eval-status");
  if (!input || !btn || !statusEl) return;

  const description = input.value.trim();
  if (description.length < 3) {
    statusEl.textContent = "Please enter a mission description (at least 3 characters).";
    statusEl.className = "muted-note status-error";
    state.aiWeightStatus = "Error";
    onSyncSummaries?.();
    return;
  }

  btn.disabled = true;
  btn.textContent = "Evaluating Weights...";
  statusEl.textContent = "Requesting parameter weights from AI model...";
  statusEl.className = "muted-note";
  state.aiWeightStatus = "Evaluating...";
  onSyncSummaries?.();

  try {
    const data = await evaluateMissionWeightsApi(description);
    state.weights = { ...data.weights };
    state.aiWeightStatus = "Applied";
    await onWeightsApplied();
    statusEl.textContent = "AI parameter weights applied and globe updated.";
    statusEl.className = "muted-note status-ok";
  } catch (err) {
    state.aiWeightStatus = "Error";
    statusEl.textContent = err.message || "Failed to evaluate weights.";
    statusEl.className = "muted-note status-error";
  } finally {
    btn.disabled = false;
    btn.textContent = "Evaluate Weights with AI";
    onSyncSummaries?.();
  }
}
