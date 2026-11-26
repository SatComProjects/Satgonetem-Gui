/** Server-side experiment runs page controller. */
import { api } from "./api.js?v=4";
import { byId, downloadBlob, setStatus } from "./dom.js";
import { escapeHtml } from "./escape.js";
import {
  DEFAULT_SCENARIO,
  artifactLabel,
  compareTableRows,
  diffScenarioLines,
  experimentModeLabel,
  experimentStatusLabel,
  experimentSummaryText,
  formatBps,
  formatExperimentDate,
  sampleSeries,
} from "./experiments_model.js?v=2";

const POLL_INTERVAL_MS = 1000;
const DETAIL_POLL_INTERVAL_MS = 2000;
const DETAIL_RETRY_MS = 3000;
const MAX_COMPARE = 4;
const CHART_COLORS = ["#3da9fc", "#4ade80", "#fbbf24", "#f87171"];

let pollTimer = null;
let startBusy = false;
let runs = [];
const selectedRuns = new Set();

let detailRunId = null;
let detailRun = null;
let detailTimer = null;
let detailBusy = false;
let detailChart = null;
let detailReportLoaded = false;

let compareChart = null;
let compareData = [];
let compareMetric = "tx_bps";

function setMessage(text, isError = false) {
  setStatus(byId("experiments-msg"), text, isError);
}

function setStartStatus(text, isError = false) {
  setStatus(byId("experiment-start-status"), text, isError);
}

function setDetailStatus(text, isError = false) {
  setStatus(byId("experiment-detail-status"), text, isError);
}

function setChartMessage(id, text, isError = false) {
  setStatus(byId(id), text, isError);
}

function clearTimeoutIfSet(timer) {
  if (timer !== null) clearTimeout(timer);
}

function stopListPoll() {
  clearTimeoutIfSet(pollTimer);
  pollTimer = null;
}

function stopDetailPoll() {
  clearTimeoutIfSet(detailTimer);
  detailTimer = null;
}

function destroyChart(chart) {
  if (!chart) return null;
  try {
    chart.destroy();
  } catch {
    /* a detached chart is harmless */
  }
  return null;
}

function cssColor(name, fallback) {
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value || fallback;
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
  const selectable = run.status !== "running";
  const checked = selectedRuns.has(run.run_id);
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

function updateCompareBar() {
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

function renderRuns(records) {
  const list = byId("experiments-list");
  const empty = byId("experiments-empty");
  if (!list) return;
  runs = Array.isArray(records) ? records : [];
  const terminalIds = new Set(
    runs.filter((run) => run.status !== "running").map((run) => run.run_id),
  );
  for (const id of [...selectedRuns]) {
    if (!terminalIds.has(id)) selectedRuns.delete(id);
  }
  list.innerHTML = runs.map(runRow).join("");
  if (empty) empty.hidden = runs.length > 0;
  updateCompareBar();
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

/* ------------------------------------------------------------------ */
/* Detail panel                                                        */
/* ------------------------------------------------------------------ */

function detailStat(label, value) {
  return `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`;
}

function summaryMetric(run, key) {
  const metrics = run?.summary?.metrics;
  const value = Number(metrics?.[key]);
  return Number.isFinite(value) ? value : null;
}

function renderDetailStats(run, metricsInfo) {
  const stats = byId("experiment-detail-stats");
  if (!stats) return;
  const summary = run?.summary || {};
  const flows = summary.flows || {};
  const samples =
    metricsInfo && !metricsInfo.error
      ? metricsInfo.total
      : summaryMetric(run, "samples") ?? 0;
  const simTime = summaryMetric(run, "sim_time_s");
  const rows = [
    detailStat("Status", experimentStatusLabel(run.status)),
    detailStat("Mode", experimentModeLabel(run.mode)),
    detailStat("Started", formatExperimentDate(run.started_at)),
    detailStat("Finished", formatExperimentDate(run.finished_at)),
    detailStat("Samples", String(samples)),
    detailStat("Simulation time", simTime === null ? "\u2014" : `${simTime} s`),
    detailStat(
      "Flows",
      Number.isFinite(Number(flows.count)) ? String(Number(flows.count)) : "\u2014",
    ),
    detailStat(
      "Flow errors",
      Number.isFinite(Number(flows.errors))
        ? String(Number(flows.errors))
        : "\u2014",
    ),
  ];
  const connectivity = summary.connectivity;
  if (connectivity && Number.isFinite(Number(connectivity.reachable))) {
    rows.push(
      detailStat(
        "Connectivity",
        `${Number(connectivity.reachable)}/${Number(connectivity.pairs)} reachable`,
      ),
    );
  }
  rows.push(detailStat("Artifacts", String((run.artifacts || []).length)));
  stats.innerHTML = rows.join("");
}

function renderDetailArtifacts(run) {
  const container = byId("experiment-detail-artifacts");
  if (!container) return;
  container.innerHTML = artifactButtons(run);
}

function renderDetailText(scenario, report) {
  const scenarioElement = byId("experiment-detail-scenario");
  if (scenarioElement) scenarioElement.textContent = scenario || "";
  const reportElement = byId("experiment-detail-report");
  if (reportElement) reportElement.textContent = report || "";
}

function renderDetailChart(samples) {
  const canvas = byId("experiment-detail-chart");
  if (!canvas) return;
  detailChart = destroyChart(detailChart);
  const series = sampleSeries(samples);
  if (!series.length) {
    setChartMessage("experiment-detail-chart-msg", "No metric samples yet.");
    return;
  }
  if (typeof window.Chart === "undefined") {
    setChartMessage(
      "experiment-detail-chart-msg",
      `${series.length} metric samples loaded; Chart.js is unavailable in this browser.`,
      true,
    );
    return;
  }
  const accent = cssColor("--accent", "#3da9fc");
  const ok = cssColor("--ok", "#4ade80");
  const text = cssColor("--muted", "#8aa0b7");
  detailChart = new window.Chart(canvas, {
    type: "line",
    data: {
      datasets: [
        {
          label: "TX",
          data: series.map((point) => ({ x: point.sim_time_s, y: point.tx_bps })),
          borderColor: accent,
          backgroundColor: accent,
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.2,
        },
        {
          label: "RX",
          data: series.map((point) => ({ x: point.sim_time_s, y: point.rx_bps })),
          borderColor: ok,
          backgroundColor: ok,
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      parsing: false,
      interaction: { mode: "nearest", intersect: false },
      plugins: {
        legend: { labels: { color: text } },
      },
      scales: {
        x: {
          type: "linear",
          title: { display: true, text: "Simulation time (s)", color: text },
          ticks: { color: text },
          grid: { color: "rgba(138, 160, 183, 0.15)" },
        },
        y: {
          beginAtZero: true,
          title: { display: true, text: "Link traffic", color: text },
          ticks: {
            color: text,
            callback: (value) => formatBps(value),
          },
          grid: { color: "rgba(138, 160, 183, 0.15)" },
        },
      },
    },
  });
  setChartMessage("experiment-detail-chart-msg", `${series.length} metric samples.`);
}

async function fetchDetailMetrics(runId) {
  try {
    const data = await api.get(
      `/api/experiments/${encodeURIComponent(runId)}/metrics?tail=300`,
      { timeout: 30000 },
    );
    const samples = Array.isArray(data.samples) ? data.samples : [];
    return {
      samples,
      total: Number.isFinite(Number(data.total)) ? Number(data.total) : samples.length,
    };
  } catch (error) {
    return { samples: [], total: 0, error };
  }
}

async function fetchDetailText(run) {
  const artifacts = Array.isArray(run.artifacts) ? run.artifacts : [];
  let scenario = byId("experiment-detail-scenario")?.textContent || "";
  let report = byId("experiment-detail-report")?.textContent || "";
  if (artifacts.includes("scenario.yaml")) {
    try {
      scenario = (
        await api.get(
          `/api/experiments/${encodeURIComponent(run.run_id)}/artifacts/scenario.yaml`,
          { timeout: 30000 },
        )
      ).content;
    } catch {
      /* keep the text already on screen */
    }
  }
  if (artifacts.includes("report.md") && !detailReportLoaded) {
    try {
      report = (
        await api.get(
          `/api/experiments/${encodeURIComponent(run.run_id)}/artifacts/report.md`,
          { timeout: 30000 },
        )
      ).content;
      detailReportLoaded = true;
    } catch {
      /* the report is best-effort */
    }
  }
  renderDetailText(scenario, report);
}

async function refreshDetail(full = false) {
  if (!detailRunId || detailBusy) return;
  detailBusy = true;
  const runId = detailRunId;
  try {
    const run = await api.get(`/api/experiments/${encodeURIComponent(runId)}`);
    if (detailRunId !== runId) return;
    const previouslyRunning = detailRun?.status === "running";
    detailRun = run;
    if (previouslyRunning && run.status !== "running") {
      loadRuns();
    }
    const title = byId("experiment-detail-title");
    if (title) title.textContent = run.name || run.run_id;
    const sub = byId("experiment-detail-sub");
    if (sub) {
      sub.textContent = `${experimentModeLabel(run.mode)} \u00b7 started ${formatExperimentDate(run.started_at)}`;
    }
    const errors = Array.isArray(run.errors) ? run.errors : [];
    setDetailStatus(
      errors.length
        ? `${experimentStatusLabel(run.status)} \u00b7 ${errors.join("; ")}`
        : experimentStatusLabel(run.status),
      run.status === "error",
    );
    const metricsInfo = await fetchDetailMetrics(runId);
    if (detailRunId !== runId) return;
    renderDetailStats(run, metricsInfo);
    renderDetailArtifacts(run);
    renderDetailChart(metricsInfo.samples);
    if (metricsInfo.error) {
      setChartMessage(
        "experiment-detail-chart-msg",
        `Metrics unavailable: ${metricsInfo.error.message || metricsInfo.error}`,
        true,
      );
    }
    if (full || run.status !== "running") {
      await fetchDetailText(run);
    }
    if (detailRunId !== runId) return;
    stopDetailPoll();
    if (run.status === "running") {
      detailTimer = setTimeout(
        () => startDetailRefresh(false),
        DETAIL_POLL_INTERVAL_MS,
      );
    }
  } catch (error) {
    if (detailRunId !== runId) return;
    setDetailStatus(
      `Could not refresh run: ${error.message || error}`,
      true,
    );
    stopDetailPoll();
    if (detailRun && detailRun.status === "running") {
      detailTimer = setTimeout(() => startDetailRefresh(false), DETAIL_RETRY_MS);
    }
  } finally {
    detailBusy = false;
  }
}

function startDetailRefresh(full) {
  if (detailBusy) {
    detailTimer = setTimeout(() => startDetailRefresh(full), 200);
    return;
  }
  refreshDetail(full);
}

function closeDetail() {
  stopDetailPoll();
  detailRunId = null;
  detailRun = null;
  detailReportLoaded = false;
  detailChart = destroyChart(detailChart);
  const panel = byId("experiment-detail");
  if (panel) panel.hidden = true;
  const stats = byId("experiment-detail-stats");
  if (stats) stats.innerHTML = "";
  renderDetailText("", "");
  setChartMessage("experiment-detail-chart-msg", "");
}

function openDetail(runId) {
  closeCompare();
  stopDetailPoll();
  detailRunId = runId;
  detailRun = null;
  detailReportLoaded = false;
  detailChart = destroyChart(detailChart);
  const panel = byId("experiment-detail");
  if (panel) panel.hidden = false;
  const title = byId("experiment-detail-title");
  if (title) title.textContent = "Run detail";
  const sub = byId("experiment-detail-sub");
  if (sub) sub.textContent = runId;
  setDetailStatus("Loading run...");
  renderDetailText("", "");
  setChartMessage("experiment-detail-chart-msg", "");
  startDetailRefresh(true);
  panel?.scrollIntoView({ block: "start" });
}

/* ------------------------------------------------------------------ */
/* Comparison panel                                                    */
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
  const text = cssColor("--muted", "#8aa0b7");
  compareChart = new window.Chart(canvas, {
    type: "line",
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      parsing: false,
      interaction: { mode: "nearest", intersect: false },
      plugins: {
        legend: { labels: { color: text } },
      },
      scales: {
        x: {
          type: "linear",
          title: { display: true, text: "Simulation time (s)", color: text },
          ticks: { color: text },
          grid: { color: "rgba(138, 160, 183, 0.15)" },
        },
        y: {
          beginAtZero: compareMetric !== "avg_loss_percent",
          title: {
            display: true,
            text: byId("experiment-compare-metric")?.selectedOptions?.[0]?.textContent || "",
            color: text,
          },
          ticks: {
            color: text,
            callback: (value) => metricTick(value, compareMetric),
          },
          grid: { color: "rgba(138, 160, 183, 0.15)" },
        },
      },
    },
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

async function openCompare() {
  const chosen = runs.filter(
    (run) => selectedRuns.has(run.run_id) && run.status !== "running",
  );
  if (chosen.length < 2) {
    setMessage("Select at least two finished runs to compare.", true);
    return;
  }
  if (chosen.length > MAX_COMPARE) {
    setMessage(`Select at most ${MAX_COMPARE} runs to compare.`, true);
    return;
  }
  closeDetail();
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
      let samples = [];
      let scenario = "";
      try {
        const data = await api.get(
          `/api/experiments/${encodeURIComponent(runId)}/metrics?tail=2000`,
          { timeout: 30000 },
        );
        samples = Array.isArray(data.samples) ? data.samples : [];
      } catch (error) {
        failures.push(error.message || String(error));
      }
      try {
        scenario = (
          await api.get(
            `/api/experiments/${encodeURIComponent(runId)}/artifacts/scenario.yaml`,
            { timeout: 30000 },
          )
        ).content;
      } catch {
        scenario = "";
      }
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

function closeCompare() {
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

/* ------------------------------------------------------------------ */
/* Wiring                                                              */
/* ------------------------------------------------------------------ */

function toggleSelection(runId, checked, input) {
  if (checked) {
    if (selectedRuns.size >= MAX_COMPARE) {
      input.checked = false;
      setMessage(`Select at most ${MAX_COMPARE} runs to compare.`, true);
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
  setMessage("");
  updateCompareBar();
}

function initializeScenario() {
  const textarea = byId("experiment-scenario");
  if (textarea && !textarea.value.trim()) {
    textarea.value = DEFAULT_SCENARIO;
  }
}

const list = byId("experiments-list");
list?.addEventListener("change", (event) => {
  const checkbox = event.target.closest("input[data-select]");
  if (!checkbox) return;
  toggleSelection(checkbox.dataset.select, checkbox.checked, checkbox);
});

document.addEventListener("click", (event) => {
  const detailButton = event.target.closest("[data-detail]");
  if (detailButton) {
    openDetail(detailButton.dataset.detail);
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
byId("experiment-compare-btn")?.addEventListener("click", openCompare);
byId("experiment-clear-selection")?.addEventListener("click", () => {
  selectedRuns.clear();
  renderRuns(runs);
});
byId("experiment-compare-metric")?.addEventListener("change", (event) => {
  compareMetric = event.target.value;
  if (compareData.length) renderCompareChart();
});

function cleanup() {
  stopListPoll();
  stopDetailPoll();
  detailChart = destroyChart(detailChart);
  compareChart = destroyChart(compareChart);
}

window.addEventListener("pagehide", cleanup, { once: true });

initializeScenario();
loadRuns();
