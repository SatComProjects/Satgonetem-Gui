/** Connectivity matrix page controller. */
import { api } from "./api.js?v=4";
import { byId, downloadBlob, setStatus } from "./dom.js";
import { escapeHtml } from "./escape.js";
import {
  formatLoss,
  formatRtt,
  lossBucket,
  pairCount,
  resultMap,
  summaryText,
} from "./connectivity_model.js?v=1";

const MAX_NODES = 32;
const POLL_INTERVAL_MS = 1000;

function setMessage(text, isError = false) {
  setStatus(byId("connectivity-msg"), text, isError);
}

function setRunStatus(text, isError = false) {
  setStatus(byId("connectivity-status"), text, isError);
}

const state = {
  nodes: [],
  selected: new Set(),
  jobId: null,
  pollTimer: null,
  busy: false,
  latest: null,
};

function availableNodes() {
  return state.nodes;
}

function nodeLabel(node) {
  if (node.label) return node.label;
  return node.name;
}

function renderNodeList() {
  const container = byId("connectivity-nodes");
  if (!container) return;
  if (!state.nodes.length) {
    container.innerHTML =
      '<p class="muted">No addressable nodes. Load a project and enable satellite endpoints if needed.</p>';
    updateSelectionUi();
    return;
  }
  container.innerHTML = state.nodes
    .map((node) => {
      const name = escapeHtml(node.name);
      const checked = state.selected.has(node.name) ? " checked" : "";
      return `
        <label class="conn-node">
          <input type="checkbox" data-node-name="${name}"${checked}>
          <span>${escapeHtml(nodeLabel(node))}</span>
        </label>`;
    })
    .join("");
  updateSelectionUi();
}

function updateSelectionUi() {
  const count = state.selected.size;
  const pairs = pairCount(count);
  const countElement = byId("connectivity-node-count");
  if (countElement) {
    countElement.textContent = `${count} selected \u00b7 ${pairs} ordered pair${pairs === 1 ? "" : "s"}`;
  }
  const start = byId("connectivity-start");
  if (start) start.disabled = state.busy || count < 2 || count > MAX_NODES;
}

function selectDefaults() {
  const ordered = [
    ...state.nodes.filter((node) => node.type === "ground_station"),
    ...state.nodes.filter((node) => node.type !== "ground_station"),
  ];
  state.selected = new Set(ordered.slice(0, Math.min(8, MAX_NODES)).map((node) => node.name));
  if (state.selected.size < 2 && state.nodes.length >= 2) {
    state.selected = new Set(state.nodes.slice(0, 2).map((node) => node.name));
  }
}

async function loadNodes() {
  try {
    const data = await api.get("/api/traffic/nodes");
    state.nodes = Array.isArray(data?.nodes) ? data.nodes : [];
    selectDefaults();
    renderNodeList();
    if (state.nodes.length < 2) {
      setMessage(
        "At least two addressable traffic endpoints are required. Enable satellite endpoints if needed.",
        true,
      );
    } else {
      setMessage("");
    }
  } catch (error) {
    state.nodes = [];
    state.selected.clear();
    renderNodeList();
    setMessage(
      `Could not load addressable nodes: ${error.message || error}`,
      true,
    );
  }
}

function selectedNames() {
  return [...state.selected];
}

function startJob() {
  if (state.busy) return;
  const nodes = selectedNames();
  if (nodes.length < 2) {
    setMessage("Select at least two addressable nodes.", true);
    return;
  }
  if (nodes.length > MAX_NODES) {
    setMessage(`Select at most ${MAX_NODES} nodes.`, true);
    return;
  }

  state.busy = true;
  state.jobId = null;
  state.latest = null;
  updateSelectionUi();
  const statusCard = byId("connectivity-status-card");
  if (statusCard) statusCard.hidden = false;
  const progress = byId("connectivity-progress");
  if (progress) progress.hidden = false;
  const exportCsv = byId("connectivity-export-csv");
  const exportJson = byId("connectivity-export-json");
  if (exportCsv) exportCsv.hidden = true;
  if (exportJson) exportJson.hidden = true;
  const heatmap = byId("connectivity-heatmap");
  if (heatmap) heatmap.replaceChildren();
  const empty = byId("connectivity-empty");
  if (empty) empty.hidden = false;
  setRunStatus("Starting connectivity check...");

  api
    .post(
      "/api/diagnostics/connectivity",
      {
        nodes,
        ping_count: Number(byId("connectivity-ping-count")?.value) || 10,
        max_workers: Number(byId("connectivity-max-workers")?.value) || 32,
        flow_timeout_seconds: Number(byId("connectivity-timeout")?.value) || 60,
      },
      { timeout: 600000 },
    )
    .then((data) => {
      state.jobId = data.job_id;
      setRunStatus("Running connectivity check...");
      pollJob();
    })
    .catch((error) => {
      state.busy = false;
      updateSelectionUi();
      const progress = byId("connectivity-progress");
      if (progress) progress.hidden = true;
      setRunStatus("Connectivity check failed to start.", true);
      setMessage(error.message || "Could not start connectivity check.", true);
    });
}

function clearPoll() {
  if (state.pollTimer !== null) {
    clearTimeout(state.pollTimer);
    state.pollTimer = null;
  }
}

async function pollJob() {
  if (!state.jobId) return;
  try {
    const data = await api.get(
      `/api/diagnostics/connectivity/${encodeURIComponent(state.jobId)}`,
    );
    state.latest = data;
    if (data.status === "running") {
      setRunStatus(`Running ${data.pair_count || 0} ordered pings...`);
      const summary = byId("connectivity-summary");
      if (summary) {
        summary.textContent = `${data.nodes?.length || state.selected.size} nodes \u00b7 ${data.pair_count || 0} ordered pairs`;
      }
      state.pollTimer = setTimeout(pollJob, POLL_INTERVAL_MS);
      return;
    }
    state.busy = false;
    updateSelectionUi();
    const progress = byId("connectivity-progress");
    if (progress) progress.hidden = true;
    if (data.status === "error") {
      setRunStatus("Connectivity check failed.", true);
      setMessage(data.error || "Connectivity check failed.", true);
      return;
    }
    if (data.status === "done") {
      setRunStatus("Connectivity check complete.");
      setMessage("");
      renderMatrix(data);
    }
  } catch (error) {
    state.busy = false;
    updateSelectionUi();
    const progress = byId("connectivity-progress");
    if (progress) progress.hidden = true;
    setRunStatus("Connectivity status refresh failed.", true);
    setMessage(error.message || "Could not refresh connectivity status.", true);
  }
}

function renderMatrix(data) {
  const heatmap = byId("connectivity-heatmap");
  const summary = byId("connectivity-summary");
  const empty = byId("connectivity-empty");
  if (!heatmap) return;
  const nodes = Array.isArray(data.nodes) ? data.nodes : [];
  const results = resultMap(data.results);
  if (summary) summary.textContent = summaryText(data.summary, data.elapsed_ms);
  if (!nodes.length) {
    heatmap.replaceChildren();
    if (empty) {
      empty.hidden = false;
      empty.textContent = "No matrix was returned.";
    }
    return;
  }
  if (empty) empty.hidden = true;
  const header = nodes
    .map((node) => `<th scope="col">${escapeHtml(node)}</th>`)
    .join("");
  const rows = nodes
    .map((source) => {
      const cells = nodes
        .map((destination) => {
          if (source === destination) {
            return '<td class="conn-self">\u2014</td>';
          }
          const result = results.get(`${source}\u0000${destination}`);
          if (!result) {
            return '<td class="conn-cell missing">\u2014</td>';
          }
          const bucket = lossBucket(
            result.packet_loss_percent,
            result.reachable,
          );
          const title =
            `${source} \u2192 ${destination}\n` +
            `reachable: ${result.reachable ? "yes" : "no"}\n` +
            `loss: ${formatLoss(result.packet_loss_percent)}\n` +
            `rtt avg: ${formatRtt(result.rtt_avg_ms)}` +
            (result.error ? `\nerror: ${result.error}` : "");
          return (
            `<td class="conn-cell ${bucket}" title="${escapeHtml(title)}">` +
            `${escapeHtml(formatLoss(result.packet_loss_percent))}` +
            `<span>${escapeHtml(formatRtt(result.rtt_avg_ms))}</span>` +
            "</td>"
          );
        })
        .join("");
      return `<tr><th scope="row">${escapeHtml(source)}</th>${cells}</tr>`;
    })
    .join("");
  heatmap.innerHTML =
    `<table class="conn-matrix"><thead><tr><th class="conn-corner">From \\ To</th>${header}</tr></thead>` +
    `<tbody>${rows}</tbody></table>`;
  const exportCsv = byId("connectivity-export-csv");
  const exportJson = byId("connectivity-export-json");
  if (exportCsv) exportCsv.hidden = false;
  if (exportJson) exportJson.hidden = false;
}

async function exportMatrix(format) {
  if (!state.jobId) return;
  try {
    const data = await api.get(
      `/api/diagnostics/connectivity/${encodeURIComponent(state.jobId)}/export?format=${encodeURIComponent(format)}`,
      { timeout: 60000 },
    );
    downloadBlob(
      data.filename || `connectivity.${format}`,
      data.content,
      data.content_type || "text/csv",
    );
    setMessage(`Exported ${format.toUpperCase()}.`);
  } catch (error) {
    setMessage(error.message || `Could not export ${format}.`, true);
  }
}

const list = byId("connectivity-nodes");
if (list) {
  list.addEventListener("change", (event) => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement) || !input.dataset.nodeName) return;
    if (input.checked) {
      if (state.selected.size >= MAX_NODES) {
        input.checked = false;
        setMessage(`Select at most ${MAX_NODES} nodes.`, true);
        return;
      }
      state.selected.add(input.dataset.nodeName);
    } else {
      state.selected.delete(input.dataset.nodeName);
    }
    setMessage("");
    updateSelectionUi();
  });
}

byId("connectivity-select-all")?.addEventListener("click", () => {
  state.selected = new Set(state.nodes.slice(0, MAX_NODES).map((node) => node.name));
  renderNodeList();
  if (state.nodes.length > MAX_NODES) {
    setMessage(`Selected the first ${MAX_NODES} nodes; the matrix limit is ${MAX_NODES}.`);
  }
});
byId("connectivity-clear")?.addEventListener("click", () => {
  state.selected.clear();
  renderNodeList();
  setMessage("");
});
byId("connectivity-start")?.addEventListener("click", startJob);
byId("connectivity-export-csv")?.addEventListener("click", () => exportMatrix("csv"));
byId("connectivity-export-json")?.addEventListener("click", () => exportMatrix("json"));
window.addEventListener("pagehide", clearPoll, { once: true });

loadNodes();
