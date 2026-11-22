/** Server-side experiment runs page controller. */
import { api } from "./api.js?v=4";
import { escapeHtml } from "./escape.js";
import {
  DEFAULT_SCENARIO,
  artifactLabel,
  experimentModeLabel,
  experimentStatusLabel,
  experimentSummaryText,
  formatExperimentDate,
} from "./experiments_model.js?v=1";

const POLL_INTERVAL_MS = 1000;

function byId(id) {
  return document.getElementById(id);
}

function setMessage(text, isError = false) {
  const element = byId("experiments-msg");
  if (!element) return;
  element.textContent = text;
  element.style.color = isError ? "var(--bad)" : "var(--muted)";
}

function setStartStatus(text, isError = false) {
  const element = byId("experiment-start-status");
  if (!element) return;
  element.textContent = text;
  element.style.color = isError ? "var(--bad)" : "var(--muted)";
}

let pollTimer = null;
let activeRunId = null;
let busy = false;

function clearPoll() {
  if (pollTimer !== null) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

function artifactButtons(run) {
  const artifacts = Array.isArray(run.artifacts) ? run.artifacts : [];
  if (!artifacts.length) return "";
  const id = escapeHtml(run.run_id);
  return artifacts
    .map(
      (name) =>
        `<button type="button" class="button small secondary" data-run-id="${id}" data-artifact="${escapeHtml(name)}">${escapeHtml(artifactLabel(name))}</button>`,
    )
    .join("");
}

function runRow(run) {
  const id = escapeHtml(run.run_id);
  const errors = Array.isArray(run.errors) ? run.errors : [];
  return `
    <article class="experiment-run" data-run-id="${id}">
      <div class="experiment-head">
        <div class="experiment-title">
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
      <div class="experiment-artifacts">${artifactButtons(run)}</div>
    </article>`;
}

function renderRuns(runs) {
  const list = byId("experiments-list");
  const empty = byId("experiments-empty");
  if (!list) return;
  const records = Array.isArray(runs) ? runs : [];
  list.innerHTML = records.map(runRow).join("");
  if (empty) empty.hidden = records.length > 0;
}

async function loadRuns() {
  try {
    const data = await api.get("/api/experiments");
    renderRuns(data.runs);
  } catch (error) {
    setMessage(`Could not list experiments: ${error.message || error}`, true);
  }
}

function applyRun(run) {
  setStartStatus(
    `${experimentStatusLabel(run.status)} \u00b7 ${experimentSummaryText(run.summary)}`,
    run.status === "error",
  );
}

async function pollRun(runId) {
  try {
    const run = await api.get(`/api/experiments/${encodeURIComponent(runId)}`);
    applyRun(run);
    if (run.status === "running") {
      pollTimer = setTimeout(() => pollRun(runId), POLL_INTERVAL_MS);
      return;
    }
    busy = false;
    const button = byId("experiment-run");
    if (button) button.disabled = false;
    await loadRuns();
  } catch (error) {
    busy = false;
    const button = byId("experiment-run");
    if (button) button.disabled = false;
    setStartStatus(
      `Run status refresh failed: ${error.message || error}`,
      true,
    );
  }
}

async function startExperiment() {
  if (busy) return;
  const scenario = byId("experiment-scenario")?.value || "";
  if (!scenario.trim()) {
    setMessage("Paste a scenario YAML first.", true);
    return;
  }
  busy = true;
  const button = byId("experiment-run");
  if (button) button.disabled = true;
  setStartStatus("Starting experiment...");
  clearPoll();
  try {
    const data = await api.post(
      "/api/experiments",
      {
        scenario_yaml: scenario,
        mode: byId("experiment-mode")?.value || "offline",
      },
      { timeout: 600000 },
    );
    activeRunId = data.run_id;
    setStartStatus("Running experiment...");
    pollRun(activeRunId);
  } catch (error) {
    busy = false;
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
    const blob = new Blob([data.content], {
      type: data.content_type || "text/plain",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = data.filename || name;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
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

const list = byId("experiments-list");
if (list) {
  list.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-artifact]");
    if (!button) return;
    downloadArtifact(button.dataset.runId, button.dataset.artifact);
  });
}

byId("experiment-run")?.addEventListener("click", startExperiment);
window.addEventListener("pagehide", clearPoll, { once: true });

initializeScenario();
loadRuns();
