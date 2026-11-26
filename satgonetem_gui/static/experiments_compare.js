/**
 * Experiment comparison panel.
 *
 * Owns run selection (the checkbox set, the compare bar, and the four-run
 * cap), the comparison table/chart/scenario diff, and the panel's open/close
 * lifecycle.
 *
 * `openCompare` receives `closeDetail` from the page orchestrator instead of
 * importing `experiments_detail.js`, so the two panels never form a cycle.
 */
import { api } from "./api.js?v=4";
import { byId } from "./dom.js";
import { escapeHtml } from "./escape.js";
import {
  createLineChart,
  destroyChart,
  setChartMessage,
  setPageMessage,
} from "./experiments_shared.js?v=1";
import {
  compareTableRows,
  diffScenarioLines,
  formatBps,
  sampleSeries,
} from "./experiments_model.js?v=2";

const MAX_COMPARE = 4;
const CHART_COLORS = ["#3da9fc", "#4ade80", "#fbbf24", "#f87171"];

const selectedRuns = new Set();
let compareChart = null;
let compareData = [];
let compareMetric = "tx_bps";

/* ------------------------------------------------------------------ */
/* Selection                                                           */
/* ------------------------------------------------------------------ */

/** @param {string} runId - Run id. @returns {boolean} */
export function isRunSelected(runId) {
  return selectedRuns.has(runId);
}

function updateCompareBar(runs) {
  const terminalCount = runs.filter((run) => run.status !== "running").length;
  const bar = byId("experiment-compare-bar");
  const count = byId("experiment-selection-count");
  const button = byId("experiment-compare-btn");
  if (count) {
    const total = selectedRuns.size;
    count.textContent = `${total} selected`;
  }
  if (button) button.disabled = selectedRuns.size < 2;
  if (bar) bar.hidden = terminalCount < 2 && selectedRuns.size === 0;
}

/**
 * Drop selections for runs that are no longer finished and refresh the bar.
 *
 * Called by the list renderer before rows are re-rendered so stale checked
 * boxes never appear.
 *
 * @param {object[]} runs - Current run records.
 */
export function syncCompareSelection(runs) {
  const terminalIds = new Set(
    runs.filter((run) => run.status !== "running").map((run) => run.run_id),
  );
  for (const id of [...selectedRuns]) {
    if (!terminalIds.has(id)) selectedRuns.delete(id);
  }
  updateCompareBar(runs);
}

/**
 * Apply a checkbox change from the run list.
 *
 * @param {object[]} runs - Current run records.
 * @param {HTMLInputElement} input - Changed selection checkbox.
 */
export function handleSelectionChange(runs, input) {
  const runId = input.dataset.select;
  if (input.checked) {
    if (selectedRuns.size >= MAX_COMPARE) {
      input.checked = false;
      setPageMessage(`Select at most ${MAX_COMPARE} runs to compare.`, true);
      return;
    }
    selectedRuns.add(runId);
  } else {
    selectedRuns.delete(runId);
  }
  input.closest(".experiment-run")?.classList.toggle(
    "selected",
    selectedRuns.has(runId),
  );
  setPageMessage("");
  updateCompareBar(runs);
}

/** Clear every selected run (the list is re-rendered by the orchestrator). */
export function clearSelection() {
  selectedRuns.clear();
}

/* ------------------------------------------------------------------ */
/* Table, chart, and diff                                              */
/* ------------------------------------------------------------------ */

function metricValue(point, metric) {
  return Number(point?.[metric]) || 0;
}

function metricTick(value, metric) {
  if (metric === "tx_bps" || metric === "rx_bps") return formatBps(value);
  if (metric === "avg_loss_percent") return `${value}%`;
  return String(value);
}

function renderCompareTable() {
  const container = byId("experiment-compare-table");
  if (!container) return;
  const records = compareData.map((item) => item.run);
  if (!records.length) {
    container.innerHTML = "";
    return;
  }
  const rows = compareTableRows(records);
  const head = records
    .map(
      (run) =>
        `<th scope="col"><span class="exp-compare-run-name">${escapeHtml(run.name || run.run_id)}</span><span class="muted exp-compare-run-meta">${escapeHtml(run.run_id)}</span></th>`,
    )
    .join("");
  const body = rows
    .map(
      (row) =>
        `<tr><th scope="row">${escapeHtml(row.label)}</th>${row.values
          .map((value) => `<td>${escapeHtml(value)}</td>`)
          .join("")}</tr>`,
    )
    .join("");
  container.innerHTML = `<table class="exp-compare-table-el"><thead><tr><th scope="col">Metric</th>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

function renderCompareChart() {
  const canvas = byId("experiment-compare-chart");
  if (!canvas) return;
  compareChart = destroyChart(compareChart);
  const datasets = compareData.map((item, index) => ({
    label: item.run.name || item.run.run_id,
    data: item.series.map((point) => ({
      x: point.sim_time_s,
      y: metricValue(point, compareMetric),
    })),
    borderColor: CHART_COLORS[index % CHART_COLORS.length],
    backgroundColor: CHART_COLORS[index % CHART_COLORS.length],
    borderWidth: 2,
    pointRadius: 0,
    tension: 0.2,
  }));
  const hasPoints = datasets.some((dataset) => dataset.data.length > 0);
  if (!hasPoints) {
    setChartMessage(
      "experiment-compare-msg",
      "No metric samples are available for the selected runs.",
      true,
    );
    return;
  }
  if (typeof window.Chart === "undefined") {
    setChartMessage(
      "experiment-compare-msg",
      "Chart.js is unavailable in this browser; the table still shows run summaries.",
      true,
    );
    return;
  }
  compareChart = createLineChart(canvas, {
    datasets,
    yTitle: byId("experiment-compare-metric")?.selectedOptions?.[0]?.textContent || "",
    yTick: (value) => metricTick(value, compareMetric),
    beginAtZero: compareMetric !== "avg_loss_percent",
  });
  setChartMessage(
    "experiment-compare-msg",
    `${compareData.length} runs \u00b7 ${datasets.reduce((total, dataset) => total + dataset.data.length, 0)} samples.`,
  );
}

function renderCompareDiff() {
  const container = byId("experiment-compare-diff");
  if (!container) return;
  const baseline = compareData[0];
  if (!baseline) {
    container.innerHTML = "";
    return;
  }
  const blocks = compareData.slice(1).map((item) => {
    const diff = diffScenarioLines(baseline.scenario, item.scenario);
    const lines = diff
      .map((line) => {
        const prefix =
          line.kind === "add" ? "+" : line.kind === "remove" ? "-" : " ";
        return `<span class="diff-line diff-${escapeHtml(line.kind)}">${prefix} ${escapeHtml(line.text)}</span>`;
      })
      .join("\n");
    return `<details class="exp-diff-block"><summary>Scenario diff vs ${escapeHtml(baseline.run.name || baseline.run.run_id)}</summary><pre class="exp-pre exp-diff">${lines}</pre></details>`;
  });
  container.innerHTML = blocks.join("");
}

function renderCompare() {
  const sub = byId("experiment-compare-sub");
  if (sub) {
    sub.textContent = `${compareData.length} runs compared over simulation time.`;
  }
  renderCompareTable();
  renderCompareChart();
  renderCompareDiff();
}

/* ------------------------------------------------------------------ */
/* Panel lifecycle                                                     */
/* ------------------------------------------------------------------ */

async function fetchCompareSamples(runId, failures) {
  try {
    const data = await api.get(
      `/api/experiments/${encodeURIComponent(runId)}/metrics?tail=2000`,
      { timeout: 30000 },
    );
    return Array.isArray(data.samples) ? data.samples : [];
  } catch (error) {
    failures.push(error.message || String(error));
    return [];
  }
}

async function fetchCompareScenario(runId) {
  try {
    return (
      await api.get(
        `/api/experiments/${encodeURIComponent(runId)}/artifacts/scenario.yaml`,
        { timeout: 30000 },
      )
    ).content;
  } catch {
    return "";
  }
}

/**
 * Open the comparison panel for the finished runs selected in the list.
 *
 * Metrics and the scenario YAML are fetched in parallel per run; a failed
 * metrics request is recorded in `failures` and leaves that run's samples
 * empty without affecting any other run.
 *
 * @param {object[]} runs - Current run records.
 * @param {{closeDetail?: () => void}} [callbacks] - Panel coordination.
 */
export async function openCompare(runs, { closeDetail } = {}) {
  const chosen = runs.filter(
    (run) => selectedRuns.has(run.run_id) && run.status !== "running",
  );
  if (chosen.length < 2) {
    setPageMessage("Select at least two finished runs to compare.", true);
    return;
  }
  if (chosen.length > MAX_COMPARE) {
    setPageMessage(`Select at most ${MAX_COMPARE} runs to compare.`, true);
    return;
  }
  closeDetail?.();
  const panel = byId("experiment-compare");
  if (panel) panel.hidden = false;
  setChartMessage("experiment-compare-msg", "Loading metrics...");
  const table = byId("experiment-compare-table");
  if (table) table.innerHTML = "";
  const diff = byId("experiment-compare-diff");
  if (diff) diff.innerHTML = "";
  compareData = [];
  const failures = [];
  compareData = await Promise.all(
    chosen.map(async (run) => {
      const runId = run.run_id;
      const [samples, scenario] = await Promise.all([
        fetchCompareSamples(runId, failures),
        fetchCompareScenario(runId),
      ]);
      return { run, samples, series: sampleSeries(samples), scenario };
    }),
  );
  renderCompare();
  if (failures.length) {
    setChartMessage(
      "experiment-compare-msg",
      `Some metrics could not be loaded: ${failures.join("; ")}`,
      true,
    );
  }
  panel?.scrollIntoView({ block: "start" });
}

/** Close the comparison panel and clear its transient state. */
export function closeCompare() {
  compareData = [];
  compareChart = destroyChart(compareChart);
  const panel = byId("experiment-compare");
  if (panel) panel.hidden = true;
  const table = byId("experiment-compare-table");
  if (table) table.innerHTML = "";
  const diff = byId("experiment-compare-diff");
  if (diff) diff.innerHTML = "";
  setChartMessage("experiment-compare-msg", "");
}

/** Change the compared metric and re-render the chart when data is loaded. */
export function setCompareMetric(metric) {
  compareMetric = metric;
  if (compareData.length) renderCompareChart();
}

/** Destroy the comparison chart (page teardown). */
export function cleanupCompare() {
  compareChart = destroyChart(compareChart);
}
