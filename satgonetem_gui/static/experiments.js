/**
 * Server-side experiment runs page controller.
 *
 * Orchestrates the page: run list loading/polling, the start form, the default
 * scenario, artifact downloads, and page teardown. The detail and comparison
 * panels live in `experiments_detail.js` and `experiments_compare.js`; this
 * module supplies the cross-panel callbacks so those modules stay acyclic.
 */
import { api } from "./api.js?v=4";
import { byId, downloadBlob, setStatus } from "./dom.js";
import { escapeHtml } from "./escape.js";
import {
  closeCompare,
  cleanupCompare,
  clearSelection,
  handleSelectionChange,
  isRunSelected,
  openCompare,
  setCompareMetric,
  syncCompareSelection,
} from "./experiments_compare.js?v=1";
import { closeDetail, cleanupDetail, openDetail } from "./experiments_detail.js?v=1";
import {
  artifactButtons,
  setPageMessage as setMessage,
} from "./experiments_shared.js?v=1";
import {
  DEFAULT_SCENARIO,
  experimentModeLabel,
  experimentStatusLabel,
  experimentSummaryText,
  formatExperimentDate,
} from "./experiments_model.js?v=2";

const POLL_INTERVAL_MS = 1000;

let pollTimer = null;
let startBusy = false;
let runs = [];

function setStartStatus(text, isError = false) {
  setStatus(byId("experiment-start-status"), text, isError);
}

function clearTimeoutIfSet(timer) {
  if (timer !== null) clearTimeout(timer);
}

function stopListPoll() {
  clearTimeoutIfSet(pollTimer);
  pollTimer = null;
}

function runRow(run) {
  const id = escapeHtml(run.run_id);
  const errors = Array.isArray(run.errors) ? run.errors : [];
  const selectable = run.status !== "running";
  const checked = isRunSelected(run.run_id);
  return `
    <article class="experiment-run${checked ? " selected" : ""}" data-run-id="${id}">
      <div class="experiment-head">
        <div class="experiment-title">
          ${
            selectable
              ? `<span class="experiment-select-cell"><input type="checkbox" class="experiment-select" data-select="${id}"${checked ? " checked" : ""} aria-label="Select ${escapeHtml(run.name || run.run_id)} for comparison"></span>`
              : ""
          }
          <strong class="experiment-name">${escapeHtml(run.name || run.run_id)}</strong>
          <span class="experiment-mode">${escapeHtml(experimentModeLabel(run.mode))}</span>
        </div>
        <span class="experiment-status" data-status="${escapeHtml(run.status)}">${escapeHtml(experimentStatusLabel(run.status))}</span>
      </div>
      <dl class="experiment-stats">
        <div><dt>Started</dt><dd>${escapeHtml(formatExperimentDate(run.started_at))}</dd></div>
        <div><dt>Finished</dt><dd>${escapeHtml(formatExperimentDate(run.finished_at))}</dd></div>
        <div><dt>Mode</dt><dd>${escapeHtml(experimentModeLabel(run.mode))}</dd></div>
        <div><dt>Summary</dt><dd>${escapeHtml(experimentSummaryText(run.summary))}</dd></div>
      </dl>
      ${errors.length ? `<p class="experiment-errors">${escapeHtml(errors.join("; "))}</p>` : ""}
      <div class="experiment-artifacts">
        <button type="button" class="button small secondary experiment-detail-btn" data-detail="${id}">Details</button>
        ${artifactButtons(run)}
      </div>
    </article>`;
}

function renderRuns(records) {
  const list = byId("experiments-list");
  const empty = byId("experiments-empty");
  if (!list) return;
  runs = Array.isArray(records) ? records : [];
  syncCompareSelection(runs);
  list.innerHTML = runs.map(runRow).join("");
  if (empty) empty.hidden = runs.length > 0;
}

async function loadRuns() {
  try {
    const data = await api.get("/api/experiments");
    renderRuns(data.runs);
  } catch (error) {
    setMessage(`Could not list experiments: ${error.message || error}`, true);
  }
}

function applyRunStatus(run) {
  setStartStatus(
    `${experimentStatusLabel(run.status)} \u00b7 ${experimentSummaryText(run.summary)}`,
    run.status === "error",
  );
}

async function pollRun(runId) {
  try {
    const run = await api.get(`/api/experiments/${encodeURIComponent(runId)}`);
    applyRunStatus(run);
    if (run.status === "running") {
      pollTimer = setTimeout(() => pollRun(runId), POLL_INTERVAL_MS);
      return;
    }
    startBusy = false;
    const button = byId("experiment-run");
    if (button) button.disabled = false;
    await loadRuns();
  } catch (error) {
    startBusy = false;
    const button = byId("experiment-run");
    if (button) button.disabled = false;
    setStartStatus(`Run status refresh failed: ${error.message || error}`, true);
  }
}

async function startExperiment() {
  if (startBusy) return;
  const scenario = byId("experiment-scenario")?.value || "";
  if (!scenario.trim()) {
    setMessage("Paste a scenario YAML first.", true);
    return;
  }
  startBusy = true;
  const button = byId("experiment-run");
  if (button) button.disabled = true;
  setStartStatus("Starting experiment...");
  stopListPoll();
  try {
    const data = await api.post(
      "/api/experiments",
      {
        scenario_yaml: scenario,
        mode: byId("experiment-mode")?.value || "offline",
      },
      { timeout: 600000 },
    );
    setStartStatus("Running experiment...");
    await loadRuns();
    pollRun(data.run_id);
  } catch (error) {
    startBusy = false;
    if (button) button.disabled = false;
    setStartStatus("Experiment failed to start.", true);
    setMessage(error.message || "Could not start experiment.", true);
  }
}

async function downloadArtifact(runId, name) {
  try {
    const data = await api.get(
      `/api/experiments/${encodeURIComponent(runId)}/artifacts/${encodeURIComponent(name)}`,
      { timeout: 60000 },
    );
    downloadBlob(
      data.filename || name,
      data.content,
      data.content_type || "text/plain",
    );
    setMessage(`Downloaded ${data.filename || name}.`);
  } catch (error) {
    setMessage(error.message || "Could not download artifact.", true);
  }
}

function initializeScenario() {
  const textarea = byId("experiment-scenario");
  if (textarea && !textarea.value.trim()) {
    textarea.value = DEFAULT_SCENARIO;
  }
}

/* ------------------------------------------------------------------ */
/* Wiring                                                              */
/* ------------------------------------------------------------------ */

const list = byId("experiments-list");
list?.addEventListener("change", (event) => {
  const checkbox = event.target.closest("input[data-select]");
  if (!checkbox) return;
  handleSelectionChange(runs, checkbox);
});

document.addEventListener("click", (event) => {
  const detailButton = event.target.closest("[data-detail]");
  if (detailButton) {
    openDetail(detailButton.dataset.detail, {
      closeCompare,
      refreshRuns: loadRuns,
    });
    return;
  }
  const artifactButton = event.target.closest("button[data-artifact]");
  if (artifactButton) {
    downloadArtifact(
      artifactButton.dataset.runId,
      artifactButton.dataset.artifact,
    );
  }
});

byId("experiment-run")?.addEventListener("click", startExperiment);
byId("experiment-detail-close")?.addEventListener("click", closeDetail);
byId("experiment-compare-close")?.addEventListener("click", closeCompare);
byId("experiment-compare-btn")?.addEventListener("click", () => {
  openCompare(runs, { closeDetail });
});
byId("experiment-clear-selection")?.addEventListener("click", () => {
  clearSelection();
  renderRuns(runs);
});
byId("experiment-compare-metric")?.addEventListener("change", (event) => {
  setCompareMetric(event.target.value);
});

function cleanup() {
  stopListPoll();
  cleanupDetail();
  cleanupCompare();
}

window.addEventListener("pagehide", cleanup, { once: true });

initializeScenario();
loadRuns();
