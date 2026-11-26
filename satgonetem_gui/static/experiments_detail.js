/**
 * Experiment run detail panel.
 *
 * Owns the detail panel's open/refresh/close lifecycle, its stats, artifacts,
 * text, chart, and the polling/retry timers used while a run is still running.
 *
 * The orchestrator passes the two cross-panel callbacks (`closeCompare` and
 * `refreshRuns`) explicitly so this module never imports `experiments.js` or
 * `experiments_compare.js` (no cycles).
 */
import { api } from "./api.js?v=4";
import { byId, setStatus } from "./dom.js";
import { escapeHtml } from "./escape.js";
import {
  artifactButtons,
  createLineChart,
  cssColor,
  destroyChart,
  setChartMessage,
} from "./experiments_shared.js?v=1";
import {
  experimentModeLabel,
  experimentStatusLabel,
  formatBps,
  formatExperimentDate,
  sampleSeries,
} from "./experiments_model.js?v=2";

const DETAIL_POLL_INTERVAL_MS = 2000;
const DETAIL_RETRY_MS = 3000;

let detailRunId = null;
let detailRun = null;
let detailTimer = null;
let detailBusy = false;
let detailChart = null;
let detailReportLoaded = false;
let closeComparePanel = () => {};
let refreshRuns = () => {};

function setDetailStatus(text, isError = false) {
  setStatus(byId("experiment-detail-status"), text, isError);
}

function clearTimeoutIfSet(timer) {
  if (timer !== null) clearTimeout(timer);
}

function stopDetailPoll() {
  clearTimeoutIfSet(detailTimer);
  detailTimer = null;
}

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
  detailChart = createLineChart(canvas, {
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
    yTitle: "Link traffic",
    yTick: (value) => formatBps(value),
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
      refreshRuns();
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

/**
 * Open the detail panel for one run.
 *
 * @param {string} runId - Run id to display.
 * @param {{closeCompare?: () => void, refreshRuns?: () => void}} [callbacks]
 *   Panel coordination supplied by the page orchestrator.
 */
export function openDetail(runId, { closeCompare, refreshRuns: loadRuns } = {}) {
  closeComparePanel = closeCompare || (() => {});
  refreshRuns = loadRuns || (() => {});
  closeComparePanel();
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

/** Close the detail panel and clear its transient state. */
export function closeDetail() {
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

/** Stop the detail poll timer and destroy its chart (page teardown). */
export function cleanupDetail() {
  stopDetailPoll();
  detailChart = destroyChart(detailChart);
}
