/** Live traffic monitor page. */
import { api } from "./api.js?v=4";
import { escapeHtml } from "./escape.js";
import {
  appendSample,
  formatBps,
  monitorSummary,
  sampleFromUsage,
  samplesToCsv,
  samplesToJson,
} from "./traffic_monitor_model.js?v=1";

const POLL_INTERVAL_MS = 2000;

let samples = [];
let paused = false;
let inFlight = false;
let pollTimer = null;
let chart = null;

function byId(id) {
  return document.getElementById(id);
}

function setMessage(text, isError = false) {
  const element = byId("monitor-msg");
  if (!element) return;
  element.textContent = text;
  element.style.color = isError ? "var(--bad)" : "var(--muted)";
}

function setNote(text) {
  const element = byId("monitor-note");
  if (!element) return;
  element.textContent = text || "";
  element.hidden = !text;
}

function destroyChart() {
  if (!chart) return;
  try {
    chart.destroy();
  } catch {
    /* detached charts are harmless */
  }
  chart = null;
}

function renderLinks(sample) {
  const container = byId("monitor-links-table");
  const empty = byId("monitor-links-empty");
  const rows = [...(sample?.links || [])].sort(
    (left, right) => right.value_bps - left.value_bps,
  );
  if (!container) return;
  if (!rows.length) {
    container.innerHTML = "";
    if (empty) empty.hidden = false;
    return;
  }
  container.innerHTML = `<table class="mon-table"><thead><tr><th>Link</th><th>Throughput</th><th>Utilization</th><th>Capacity</th><th>Delay</th><th>Loss</th><th>Jitter</th></tr></thead><tbody>${rows
    .map(
      (link) =>
        `<tr><td>${escapeHtml(link.src)} \u2192 ${escapeHtml(link.dst)}</td>` +
        `<td>${escapeHtml(formatBps(link.value_bps))}</td>` +
        `<td>${link.utilization.toFixed(1)}%</td>` +
        `<td>${escapeHtml(formatBps(link.capacity_kbps * 1000))}</td>` +
        `<td>${link.delay_ms.toFixed(1)} ms</td>` +
        `<td>${link.loss_percent.toFixed(1)}%</td>` +
        `<td>${Math.round(link.jitter_ms)} ms</td></tr>`,
    )
    .join("")}</tbody></table>`;
  if (empty) empty.hidden = true;
}

function renderNodes(sample) {
  const container = byId("monitor-nodes-table");
  const empty = byId("monitor-nodes-empty");
  const rows = (sample?.nodes || []).slice(0, 10);
  if (!container) return;
  if (!rows.length) {
    container.innerHTML = "";
    if (empty) empty.hidden = false;
    return;
  }
  container.innerHTML = `<table class="mon-table"><thead><tr><th>Node</th><th>Throughput</th></tr></thead><tbody>${rows
    .map(
      (node) =>
        `<tr><td>${escapeHtml(node.name)}</td><td>${escapeHtml(formatBps(node.value_bps))}</td></tr>`,
    )
    .join("")}</tbody></table>`;
  if (empty) empty.hidden = true;
}

function renderChart() {
  const canvas = byId("monitor-chart");
  const message = byId("monitor-chart-msg");
  if (!canvas) return;
  destroyChart();
  if (!samples.length) {
    if (message) message.textContent = "No samples yet.";
    return;
  }
  if (typeof window.Chart === "undefined") {
    if (message) {
      message.textContent = `Chart.js is unavailable; ${samples.length} samples retained.`;
    }
    return;
  }
  const labels = samples.map((sample, index) => sample.step ?? index);
  const values = samples.map((sample) => sample.total_bps);
  chart = new window.Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Total throughput",
          data: values,
          borderColor: "#3da9fc",
          backgroundColor: "rgba(61, 169, 252, 0.18)",
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.2,
          fill: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          title: { display: true, text: "Simulation step" },
          ticks: { maxTicksLimit: 8 },
        },
        y: {
          beginAtZero: true,
          ticks: { callback: (value) => formatBps(value) },
        },
      },
    },
  });
  if (message) message.textContent = `${samples.length} samples retained.`;
}

function render(sample) {
  const summary = byId("monitor-summary");
  if (summary) summary.textContent = monitorSummary(sample, samples.length);
  setNote(sample?.available === false ? sample.note || "Link usage is unavailable." : "");
  renderLinks(sample);
  renderNodes(sample);
  renderChart();
}

async function poll() {
  if (paused || inFlight) return;
  inFlight = true;
  try {
    const [usage, links, status] = await Promise.all([
      api.get("/api/links/usage"),
      api.getAll("/api/links"),
      api.get("/api/status"),
    ]);
    if (paused) return;
    const sample = sampleFromUsage(usage, links, status);
    samples = appendSample(samples, sample);
    render(sample);
    setMessage("");
  } catch (error) {
    setMessage(
      error.status === 404
        ? "Load a project to monitor traffic."
        : error.message || "Could not sample link usage.",
      true,
    );
  } finally {
    inFlight = false;
  }
}

function togglePause() {
  paused = !paused;
  const button = byId("monitor-pause");
  if (button) {
    button.textContent = paused ? "Resume" : "Pause";
    button.setAttribute("aria-pressed", String(paused));
  }
  setMessage(paused ? "Monitoring paused." : "");
  if (!paused) poll();
}

function clearSamples() {
  samples = [];
  destroyChart();
  const summary = byId("monitor-summary");
  if (summary) summary.textContent = "";
  const links = byId("monitor-links-table");
  if (links) links.innerHTML = "";
  const nodes = byId("monitor-nodes-table");
  if (nodes) nodes.innerHTML = "";
  const emptyLinks = byId("monitor-links-empty");
  if (emptyLinks) emptyLinks.hidden = false;
  const emptyNodes = byId("monitor-nodes-empty");
  if (emptyNodes) emptyNodes.hidden = false;
  const message = byId("monitor-chart-msg");
  if (message) message.textContent = "No samples yet.";
  setNote("");
}

function download(filename, content, contentType) {
  const blob = new Blob([content], { type: contentType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

function exportCsv() {
  if (!samples.length) {
    setMessage("No samples to export.", true);
    return;
  }
  download("traffic-monitor.csv", samplesToCsv(samples), "text/csv");
  setMessage("Exported traffic-monitor.csv.");
}

function exportJson() {
  if (!samples.length) {
    setMessage("No samples to export.", true);
    return;
  }
  download("traffic-monitor.json", samplesToJson(samples), "application/json");
  setMessage("Exported traffic-monitor.json.");
}

byId("monitor-pause")?.addEventListener("click", togglePause);
byId("monitor-clear")?.addEventListener("click", clearSamples);
byId("monitor-export-csv")?.addEventListener("click", exportCsv);
byId("monitor-export-json")?.addEventListener("click", exportJson);
window.addEventListener(
  "pagehide",
  () => {
    clearInterval(pollTimer);
    destroyChart();
  },
  { once: true },
);

clearSamples();
poll();
pollTimer = setInterval(poll, POLL_INTERVAL_MS);
