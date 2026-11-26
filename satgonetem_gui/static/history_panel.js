/**
 * Traffic run-history ledger.
 *
 * History is browser-local (`localStorage`) and rendered inside the shared
 * results dialog. This module owns loading, saving, normalizing, rendering,
 * comparison, export, delete, and replay. It never imports `queue.js`: the
 * queue controller injects the `addItem` hook it needs to replay a run.
 */
import { api } from "./api.js?v=4";
import { byId, downloadBlob } from "./dom.js";
import { escapeHtml } from "./escape.js";
import {
  HISTORY_KEY,
  addHistoryRecord,
  buildHistoryRecord,
  compareRuns,
  historySummaryText,
  historyToCsv,
  historyToJson,
  normalizeHistory,
  removeHistoryRecord,
} from "./history_model.js?v=1";
import { replayQueueItem } from "./queue_model.js?v=4";
import {
  createChart,
  currentPlotGeneration,
  getPlotter,
  lineChartOptions,
} from "./traffic_plots.js?v=1";
import {
  getModalOwner,
  openModal,
  registerModalOwner,
} from "./results_modal.js?v=1";

const HISTORY_OWNER = "history";
const PROJECT_STATUS_TIMEOUT_MS = 2000;

let jqHistory = normalizeHistory(null);
let historySelection = new Set();
let historyMessage = "";
let historyMessageIsError = false;
let historyCompareMessage = "";
let historyCompareMessageIsError = false;
let historyStorageSync = false;
let historySaveFailed = false;
let addToQueue = null;
let initialized = false;

function bindHistoryButton() {
  const button = byId("jq-history");
  if (button) {
    button.addEventListener("click", openHistoryModal);
    return;
  }
  // The template owns the History button. If it is not present yet, listen on
  // the queue panel so a late-rendered button still opens the ledger.
  byId("floating-queue")?.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof Element && target.closest("#jq-history")) {
      openHistoryModal();
    }
  });
}

function loadHistory() {
  try {
    return normalizeHistory(
      JSON.parse(localStorage.getItem(HISTORY_KEY) || "null"),
    );
  } catch {
    return normalizeHistory(null);
  }
}

function refreshFromStorage() {
  if (historySaveFailed) return;
  try {
    jqHistory = normalizeHistory(
      JSON.parse(localStorage.getItem(HISTORY_KEY) || "null"),
    );
  } catch {
    /* Keep the in-memory ledger when stored history is unreadable. */
  }
}

function saveHistory() {
  historyStorageSync = true;
  try {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(jqHistory));
    historySaveFailed = false;
    return true;
  } catch {
    historySaveFailed = true;
    setHistoryMessage(
      "Experiment history could not be saved in this browser.",
      true,
    );
    return false;
  } finally {
    historyStorageSync = false;
  }
}

function historyHasJob(jobId) {
  return jqHistory.records.some((record) => record.job_id === jobId);
}

/**
 * Record one completed traffic job in the browser-local ledger.
 *
 * @param {{job_id?: string|null, kind?: string, label?: string, payload?: object, started_at?: number|null}} item
 * @param {object|null} results
 */
export function captureHistory(item, results) {
  if (!item || !item.job_id || !item.kind || !results) return;
  if (historyHasJob(item.job_id)) return;
  const record = buildHistoryRecord({
    jobId: item.job_id,
    kind: item.kind,
    label: item.label,
    payload: item.payload,
    results,
    startedAt: item.started_at,
  });
  if (!record) return;
  jqHistory = addHistoryRecord(jqHistory, record);
  saveHistory();
  refreshHistoryModal();
  fillProjectName(record.id);
}

async function fillProjectName(recordId) {
  let projectName = null;
  try {
    const status = await api.get("/api/project/status", {
      timeout: PROJECT_STATUS_TIMEOUT_MS,
    });
    if (status && typeof status.project_name === "string") {
      projectName = status.project_name;
    }
  } catch {
    // The project name is metadata; a failure must not drop the run.
    return;
  }
  if (!projectName) return;
  const current = jqHistory.records.find((record) => record.id === recordId);
  if (!current || current.project_name) return;
  jqHistory = addHistoryRecord(jqHistory, {
    ...current,
    project_name: projectName,
  });
  saveHistory();
  refreshHistoryModal();
}

function refreshHistoryModal() {
  if (getModalOwner() === HISTORY_OWNER) renderHistoryModalContents();
}

function pruneHistorySelection() {
  const ids = new Set(jqHistory.records.map((record) => record.id));
  for (const id of [...historySelection]) {
    if (!ids.has(id)) historySelection.delete(id);
  }
}

function historyCountText(count) {
  return `${count} run${count === 1 ? "" : "s"}`;
}

function historyWhenText(record) {
  const date = new Date(record.recorded_at);
  const when = Number.isFinite(date.getTime())
    ? date.toLocaleString()
    : String(record.recorded_at || "");
  const project = record.project_name ? `${record.project_name} \u00b7 ` : "";
  const duration = Number.isFinite(record.duration_ms)
    ? ` (${(record.duration_ms / 1000).toFixed(1)} s)`
    : "";
  return `${project}${when}${duration}`;
}

function historyEndpointsText(record) {
  const src = record.payload?.src ?? "";
  const dst = record.payload?.dst ?? "";
  if (!src && !dst) return "\u2014";
  return `${src} \u2192 ${dst}`;
}

function historyRowHtml(record) {
  const id = escapeHtml(record.id);
  const label = record.label || record.kind;
  const checked = historySelection.has(record.id) ? " checked" : "";
  return `
    <tr class="history-row" data-history-id="${id}">
      <td><input type="checkbox" class="history-select" data-history-id="${id}" aria-label="${escapeHtml(`Select ${label}`)}"${checked}></td>
      <td class="history-when">${escapeHtml(historyWhenText(record))}</td>
      <td class="history-kind">${escapeHtml(record.kind)}</td>
      <td class="history-endpoints">${escapeHtml(historyEndpointsText(record))}</td>
      <td class="history-summary">${escapeHtml(historySummaryText(record))}</td>
      <td class="history-actions">
        <button type="button" class="button small secondary" data-history-action="open" data-history-id="${id}">Open</button>
        <button type="button" class="button small secondary" data-history-action="replay" data-history-id="${id}">Replay</button>
        <button type="button" class="button small secondary" data-history-action="export" data-history-id="${id}">Export</button>
        <button type="button" class="button small secondary" data-history-action="delete" data-history-id="${id}">Delete</button>
      </td>
    </tr>`;
}

function historyModalHtml() {
  const records = jqHistory.records;
  const hasRecords = records.length > 0;
  const rows = records.map(historyRowHtml).join("");
  const table = hasRecords
    ? `<table class="history-table">
        <thead>
          <tr>
            <th scope="col">Select</th>
            <th scope="col">When</th>
            <th scope="col">Kind</th>
            <th scope="col">Endpoints</th>
            <th scope="col">Summary</th>
            <th scope="col">Actions</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>`
    : "";
  return `
    <div class="history-toolbar">
      <span id="history-count" class="history-count">${escapeHtml(historyCountText(records.length))}</span>
      <button type="button" class="button small secondary" id="history-export-json">Export JSON</button>
      <button type="button" class="button small secondary" id="history-export-csv">Export CSV</button>
    </div>
    <p id="history-msg" class="history-msg ${historyMessageIsError ? "queue-error" : "muted"}" role="status" aria-live="polite">${escapeHtml(historyMessage)}</p>
    <div class="history-list">
      ${table}
      <p class="history-empty muted"${hasRecords ? " hidden" : ""}>No successful runs recorded yet. Start a traffic job to build history.</p>
    </div>
    <div class="history-compare-bar">
      <button type="button" class="button small secondary" id="history-compare">Compare selected</button>
      <span id="history-compare-msg" class="${historyCompareMessageIsError ? "queue-error" : "muted"}" role="status" aria-live="polite">${escapeHtml(historyCompareMessage)}</span>
    </div>`;
}

function renderHistoryModalContents() {
  const body = byId("results-body");
  if (getModalOwner() !== HISTORY_OWNER || !body) return;
  pruneHistorySelection();
  body.innerHTML = historyModalHtml();
}

function openHistoryModal() {
  refreshFromStorage();
  historySelection = new Set();
  if (!historyMessageIsError) historyMessage = "";
  historyCompareMessage = "";
  historyCompareMessageIsError = false;
  openModal("Experiment History", historyModalHtml(), HISTORY_OWNER);
}

function setHistoryMessage(text, isError = false) {
  historyMessage = text;
  historyMessageIsError = isError;
  const element = byId("history-msg");
  if (!element) return;
  element.textContent = text;
  element.className = `history-msg ${isError ? "queue-error" : "muted"}`;
}

function setHistoryCompareMessage(text, isError = false) {
  historyCompareMessage = text;
  historyCompareMessageIsError = isError;
  const element = byId("history-compare-msg");
  if (!element) return;
  element.textContent = text;
  element.className = isError ? "queue-error" : "muted";
}

function historyFileId(record) {
  const safe = String(record?.id ?? "run")
    .replace(/[^A-Za-z0-9._-]+/g, "_")
    .replace(/^[._-]+/, "")
    .replace(/[._-]+$/, "")
    .slice(0, 100);
  return safe || "run";
}

function downloadText(filename, text, type) {
  try {
    downloadBlob(filename, text, type);
    return true;
  } catch {
    return false;
  }
}

function exportHistoryRecord(record) {
  let text;
  try {
    text = JSON.stringify(record, null, 2);
  } catch {
    setHistoryMessage("Could not export this run.", true);
    return;
  }
  const ok = downloadText(
    `sgnt-run-${historyFileId(record)}.json`,
    text,
    "application/json",
  );
  setHistoryMessage(
    ok ? "Run exported as JSON." : "Could not export this run.",
    !ok,
  );
}

function exportHistoryJson() {
  const ok = downloadText(
    "sgnt-history.json",
    historyToJson(jqHistory),
    "application/json",
  );
  setHistoryMessage(
    ok ? "History exported as JSON." : "Could not export history.",
    !ok,
  );
}

function exportHistoryCsv() {
  const ok = downloadText(
    "sgnt-history.csv",
    historyToCsv(jqHistory),
    "text/csv",
  );
  setHistoryMessage(
    ok ? "History exported as CSV." : "Could not export history.",
    !ok,
  );
}

function openHistoryRecord(record) {
  if (!record?.results) {
    setHistoryMessage("Results are not available for this run.", true);
    return;
  }
  const plot = getPlotter(record.kind);
  if (!plot) {
    setHistoryMessage(`Cannot open a ${record.kind} run.`, true);
    return;
  }
  plot({
    kind: record.kind,
    payload: record.payload || {},
    results: record.results,
  });
}

function deleteHistoryRecord(record) {
  if (!window.confirm(`Delete history run "${record.label}"?`)) return;
  jqHistory = removeHistoryRecord(jqHistory, record.id);
  historySelection.delete(record.id);
  saveHistory();
  setHistoryMessage("Run deleted.");
  renderHistoryModalContents();
}

function handleHistoryBodyClick(event) {
  const target = event.target;
  if (!(target instanceof Element)) return;
  const button = target.closest("button");
  if (!button) return;
  if (button.id === "history-export-json") {
    exportHistoryJson();
    return;
  }
  if (button.id === "history-export-csv") {
    exportHistoryCsv();
    return;
  }
  if (button.id === "history-compare") {
    compareSelectedHistory();
    return;
  }
  const action = button.dataset.historyAction;
  if (!action) return;
  const record = jqHistory.records.find(
    (entry) => entry.id === button.dataset.historyId,
  );
  if (!record) return;
  if (action === "open") openHistoryRecord(record);
  else if (action === "replay") replayHistoryRecord(record);
  else if (action === "export") exportHistoryRecord(record);
  else if (action === "delete") deleteHistoryRecord(record);
}

function replayHistoryRecord(record) {
  addToQueue(replayQueueItem(record));
  setHistoryMessage("Replay added to the queue.", false);
}

function handleHistoryBodyChange(event) {
  const target = event.target;
  if (
    !(target instanceof HTMLInputElement) ||
    !target.classList.contains("history-select")
  ) {
    return;
  }
  const id = target.dataset.historyId;
  if (!id) return;
  if (target.checked) historySelection.add(id);
  else historySelection.delete(id);
  if (historyCompareMessage) setHistoryCompareMessage("", false);
}

function formatCompareValue(value, unit) {
  if (!Number.isFinite(value)) return "-";
  return `${Number(value.toFixed(2))}${unit ? ` ${unit}` : ""}`;
}

function formatCompareDelta(delta, unit) {
  if (!Number.isFinite(delta)) return "-";
  const sign = delta > 0 ? "+" : "";
  return `${sign}${Number(delta.toFixed(2))}${unit ? ` ${unit}` : ""}`;
}

function comparisonMarkup(first, second, comparison) {
  const rows = comparison.rows
    .map((row) => {
      const deltaClass =
        row.delta === null
          ? "neutral"
          : row.delta > 0
            ? "positive"
            : row.delta < 0
              ? "negative"
              : "neutral";
      return `
        <tr>
          <td>${escapeHtml(row.label)}</td>
          <td>${escapeHtml(formatCompareValue(row.first, row.unit))}</td>
          <td>${escapeHtml(formatCompareValue(row.second, row.unit))}</td>
          <td class="history-compare-delta ${deltaClass}">${escapeHtml(formatCompareDelta(row.delta, row.unit))}</td>
        </tr>`;
    })
    .join("");
  const table = comparison.rows.length
    ? `<table class="history-compare-table">
        <thead>
          <tr>
            <th scope="col">Metric</th>
            <th scope="col">Run A</th>
            <th scope="col">Run B</th>
            <th scope="col">Delta (B - A)</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>`
    : '<p class="muted">No summary metrics are available for these runs.</p>';
  let chartNote = "";
  if (!comparison.series) {
    chartNote =
      '<p class="muted">This comparison has no time-series chart; only the summary table is shown.</p>';
  } else if (!window.Chart) {
    chartNote =
      '<p class="muted">Comparison chart unavailable because the Chart.js CDN did not load.</p>';
  }
  return `
    <div class="history-compare-grid">
      <div class="history-compare-summary">
        <div class="history-compare-runs">
          <p><strong>Run A:</strong> ${escapeHtml(first.label)} <span class="muted">${escapeHtml(historyWhenText(first))}</span></p>
          <p><strong>Run B:</strong> ${escapeHtml(second.label)} <span class="muted">${escapeHtml(historyWhenText(second))}</span></p>
          <p class="muted">Delta is Run B minus Run A.</p>
        </div>
        ${table}
      </div>
      <div class="chart-container">
        ${chartNote}
        <canvas id="history-compare-chart"></canvas>
      </div>
    </div>`;
}

function compareSelectedHistory() {
  pruneHistorySelection();
  if (historySelection.size !== 2) {
    setHistoryCompareMessage("Select exactly two runs to compare.", true);
    return;
  }
  const selected = jqHistory.records.filter((record) =>
    historySelection.has(record.id),
  );
  if (selected.length !== 2) {
    setHistoryCompareMessage("Select exactly two runs to compare.", true);
    return;
  }
  const [first, second] = selected;
  if (first.kind !== second.kind) {
    setHistoryCompareMessage(
      `Compare runs of the same kind; selected ${first.kind} and ${second.kind}.`,
      true,
    );
    return;
  }
  const comparison = compareRuns(first, second);
  const markup = comparisonMarkup(first, second, comparison);
  historySelection.clear();
  historyMessage = "";
  historyMessageIsError = false;
  historyCompareMessage = "";
  historyCompareMessageIsError = false;
  openModal("Compare Runs", markup);
  if (comparison.series && window.Chart) {
    const generation = currentPlotGeneration();
    requestAnimationFrame(() => {
      if (generation !== currentPlotGeneration()) return;
      const canvas = byId("history-compare-chart");
      if (!canvas || !window.Chart) return;
      const labels = comparison.series.first.map((_value, index) => index + 1);
      createChart(canvas, {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: "Run A",
              data: comparison.series.first,
              borderColor: "#3da9fc",
              tension: 0.2,
              pointRadius: 0,
            },
            {
              label: "Run B",
              data: comparison.series.second,
              borderColor: "#f59e0b",
              tension: 0.2,
              pointRadius: 0,
            },
          ],
        },
        options: lineChartOptions(comparison.series.label, {
          xTitle: "Sample",
        }),
      });
    });
  }
}

function handleHistoryStorage(event) {
  if (event.key !== HISTORY_KEY || historyStorageSync) return;
  jqHistory = loadHistory();
  if (getModalOwner() !== HISTORY_OWNER) return;
  pruneHistorySelection();
  renderHistoryModalContents();
}

/**
 * Wire the history ledger into the page.
 *
 * The queue controller injects `addItem` so replay adds the run to the queue
 * without this module importing `queue.js` (which would create a cycle).
 *
 * @param {{addItem?: (item: object) => string}} [hooks]
 */
export function initHistoryPanel(hooks = {}) {
  if (typeof hooks.addItem === "function") addToQueue = hooks.addItem;
  if (initialized) return;
  initialized = true;
  jqHistory = loadHistory();
  registerModalOwner(HISTORY_OWNER, {
    onBodyClick: handleHistoryBodyClick,
    onBodyChange: handleHistoryBodyChange,
  });
  bindHistoryButton();
  window.addEventListener("storage", handleHistoryStorage);
}
