/** Throughput matrix page controller. */
import { api } from "./api.js?v=4";
import { byId, downloadBlob, setStatus } from "./dom.js";
import { escapeHtml } from "./escape.js";
import {
  formatThroughput,
  heatLevel,
  matrixMax,
  matrixSummary,
} from "./traffic_matrix_model.js?v=1";

let jobId = null;
let pollTimer = null;
let busy = false;

function setMessage(text, isError = false) {
  setStatus(byId("matrix-msg"), text, isError);
}

function setProgress(text, isError = false) {
  setStatus(byId("matrix-progress"), text, isError);
}

async function loadNodes() {
  const select = byId("matrix-nodes");
  if (!select) return;
  try {
    const data = await api.get("/api/traffic/nodes");
    const nodes = Array.isArray(data?.nodes) ? data.nodes : [];
    select.replaceChildren();
    for (const node of nodes) {
      const option = document.createElement("option");
      option.value = node.name;
      option.textContent = node.label || node.name;
      select.appendChild(option);
    }
    for (const option of [...select.options].slice(0, 4)) {
      option.selected = true;
    }
    const hint = byId("matrix-node-hint");
    if (hint) {
      hint.textContent = nodes.length
        ? `${nodes.length} traffic endpoints available.`
        : "No traffic endpoints. Apply addressing and enable satellite endpoints first.";
    }
  } catch (error) {
    setMessage(
      error.status === 404
        ? "Load a project to list traffic nodes."
        : error.message || "Could not load traffic nodes.",
      true,
    );
  }
}

function selectedNodes() {
  return [...(byId("matrix-nodes")?.selectedOptions || [])].map(
    (option) => option.value,
  );
}

function renderHeatmap(job) {
  const container = byId("matrix-heatmap");
  if (!container) return;
  const nodes = Array.isArray(job.nodes) ? job.nodes : [];
  const matrix = Array.isArray(job.matrix) ? job.matrix : [];
  const max = matrixMax(matrix);
  const head = nodes
    .map((name) => `<th scope="col">${escapeHtml(name)}</th>`)
    .join("");
  const rows = nodes
    .map((source, rowIndex) => {
      const cells = nodes
        .map((destination, columnIndex) => {
          if (rowIndex === columnIndex) {
            return '<td class="matrix-diagonal">\u2014</td>';
          }
          const value = matrix[rowIndex]?.[columnIndex];
          const level = heatLevel(value, max);
          const title = `${source} \u2192 ${destination}: ${formatThroughput(value)}`;
          return `<td class="matrix-cell heat-${level}" title="${escapeHtml(title)}">${value === null || value === undefined ? "\u2014" : Number(value).toFixed(1)}</td>`;
        })
        .join("");
      return `<tr><th scope="row">${escapeHtml(source)}</th>${cells}</tr>`;
    })
    .join("");
  container.innerHTML = `<table class="matrix-table"><thead><tr><th>From \\ To</th>${head}</tr></thead><tbody>${rows}</tbody></table>`;
}

function renderJob(job) {
  const empty = byId("matrix-empty");
  const results = byId("matrix-results");
  if (empty) empty.hidden = true;
  if (results) results.hidden = false;
  const summary = byId("matrix-summary");
  if (summary) summary.textContent = matrixSummary(job);
  const failures = (job.results || []).filter(
    (item) => item.status !== "done" && item.status !== "pending",
  );
  const errors = byId("matrix-errors");
  if (errors) {
    const messages = [
      ...(job.errors || []),
      ...failures.map(
        (item) =>
          `${item.src} \u2192 ${item.dst}: ${item.error || item.status}`,
      ),
    ];
    errors.textContent = messages.join("; ");
    errors.hidden = messages.length === 0;
  }
  renderHeatmap(job);
  const csv = byId("matrix-export-csv");
  const json = byId("matrix-export-json");
  if (csv) csv.disabled = job.status === "running";
  if (json) json.disabled = job.status === "running";
}

async function poll() {
  if (!jobId) return;
  try {
    const job = await api.get(`/api/traffic/matrix/${encodeURIComponent(jobId)}`);
    renderJob(job);
    setProgress(matrixSummary(job));
    if (job.status === "running") {
      pollTimer = setTimeout(poll, 1000);
      return;
    }
    busy = false;
    const button = byId("matrix-start");
    if (button) button.disabled = false;
  } catch (error) {
    busy = false;
    const button = byId("matrix-start");
    if (button) button.disabled = false;
    setProgress(error.message || "Could not refresh the matrix.", true);
  }
}

async function startMatrix() {
  if (busy) return;
  const nodes = selectedNodes();
  if (nodes.length < 2) {
    setMessage("Select at least two nodes.", true);
    return;
  }
  if (nodes.length > 12) {
    setMessage("Select at most 12 nodes.", true);
    return;
  }
  busy = true;
  const button = byId("matrix-start");
  if (button) button.disabled = true;
  const empty = byId("matrix-empty");
  const results = byId("matrix-results");
  if (empty) empty.hidden = false;
  if (results) results.hidden = true;
  setMessage("");
  setProgress("Starting matrix...");
  try {
    const data = await api.post(
      "/api/traffic/matrix",
      {
        nodes,
        duration_s: Number(byId("matrix-duration")?.value || 1),
        concurrency: Number(byId("matrix-concurrency")?.value || 2),
      },
      { timeout: 30000 },
    );
    jobId = data.job_id;
    setProgress("Running...");
    poll();
  } catch (error) {
    busy = false;
    if (button) button.disabled = false;
    setProgress(error.message || "Could not start the matrix.", true);
  }
}

async function exportMatrix(format) {
  if (!jobId) return;
  try {
    const data = await api.get(
      `/api/traffic/matrix/${encodeURIComponent(jobId)}/export?format=${encodeURIComponent(format)}`,
    );
    downloadBlob(
      data.filename || `traffic-matrix.${format}`,
      data.content,
      data.content_type || "text/plain",
    );
    setMessage(`Downloaded ${data.filename || format}.`);
  } catch (error) {
    setMessage(error.message || "Could not export the matrix.", true);
  }
}

byId("matrix-start")?.addEventListener("click", startMatrix);
byId("matrix-export-csv")?.addEventListener("click", () => exportMatrix("csv"));
byId("matrix-export-json")?.addEventListener("click", () => exportMatrix("json"));
window.addEventListener("pagehide", () => clearTimeout(pollTimer), { once: true });

loadNodes();
