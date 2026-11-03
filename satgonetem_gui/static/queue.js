/** Shared traffic job queue, persistence, polling, and result charts. */
import { api, ApiError } from "./api.js";
import { escapeHtml } from "./escape.js";
import {
  addItem,
  activeCount,
  findItem,
  isTerminal,
  normalizeStoredItems,
  removeItem,
  startableItems,
  updateItem,
} from "./queue_model.js";

const JQ_KEY = "sgnt_traffic_queue";

const jq = { items: [], timers: {} };

function byId(id) {
  return document.getElementById(id);
}

function jqSave() {
  try {
    localStorage.setItem(JQ_KEY, JSON.stringify(jq.items));
  } catch {
    /* storage may be unavailable */
  }
}

function clearTimer(id) {
  if (jq.timers[id]) {
    clearTimeout(jq.timers[id]);
    delete jq.timers[id];
  }
}

function schedule(id, delay, callback) {
  clearTimer(id);
  jq.timers[id] = setTimeout(callback, delay);
}

function queueInit() {
  jqLoad();
  jqRender();
  bindStaticControls();
}

function bindStaticControls() {
  byId("jq-toggle")?.addEventListener("click", jqToggleCollapsed);
  byId("jq-start-all")?.addEventListener("click", jqStartAll);
  byId("jq-clear")?.addEventListener("click", jqClear);
  byId("results-close")?.addEventListener("click", closeResults);
  byId("results-backdrop")?.addEventListener("click", closeResults);
}

function jqLoad() {
  let stored = [];
  try {
    stored = normalizeStoredItems(JSON.parse(localStorage.getItem(JQ_KEY) || "[]"));
  } catch {
    stored = [];
  }
  jq.items = stored.map((item) =>
    item.status === "starting" || item.status === "scheduled"
      ? { ...item, status: "queued" }
      : item,
  );
  for (const item of jq.items) {
    if (item.status === "running" && item.job_id) {
      schedule(item.id, 0, () => jqTrack(item.id));
    }
  }
  jqSave();
}

function jqToggleCollapsed() {
  const panel = byId("floating-queue");
  if (!panel) return;
  panel.classList.toggle("collapsed");
  const icon = byId("jq-toggle-icon");
  if (icon) {
    icon.textContent = panel.classList.contains("collapsed") ? "\u25B2" : "\u25BC";
  }
}

function jqExpand() {
  const panel = byId("floating-queue");
  if (!panel) return;
  panel.classList.remove("collapsed");
  const icon = byId("jq-toggle-icon");
  if (icon) icon.textContent = "\u25BC";
}

function jqUpdateBadge() {
  const badge = byId("jq-badge");
  if (!badge) return;
  const active = activeCount(jq.items);
  badge.textContent = String(active);
  badge.style.display = active > 0 ? "inline-block" : "none";
}

function jqRender() {
  const list = byId("job-queue-list");
  if (!list) return;
  list.replaceChildren();

  if (jq.items.length === 0) {
    const empty = document.createElement("div");
    empty.className = "muted";
    empty.textContent = "No jobs queued.";
    list.appendChild(empty);
    jqUpdateBadge();
    return;
  }

  list.innerHTML = jq.items
    .map((item) => {
      const id = escapeHtml(item.id);
      const canStart = item.status === "queued" || item.status === "scheduled";
      return `
        <div class="queue-item">
          <div class="queue-item-header">
            <span class="queue-kind">${escapeHtml(item.kind)}</span>
            <span class="queue-label">${escapeHtml(item.label)}</span>
            <span class="queue-status">${escapeHtml(item.status)}</span>
          </div>
          <div class="queue-item-actions">
            ${item.status === "done" ? `<button type="button" class="button small secondary" data-action="plot" data-id="${id}">Plot</button>` : ""}
            ${canStart ? `<button type="button" class="button small" data-action="start" data-id="${id}">Start</button>` : ""}
            ${item.status === "running" ? `<button type="button" class="button small secondary" data-action="cancel" data-id="${id}">Cancel</button>` : ""}
            <button type="button" class="button small secondary" data-action="remove" data-id="${id}">Remove</button>
          </div>
        </div>`;
    })
    .join("");

  list.querySelectorAll("button[data-action]").forEach((button) => {
    button.addEventListener("click", () => {
      const id = button.dataset.id;
      switch (button.dataset.action) {
        case "plot":
          jqPlot(id);
          break;
        case "start":
          jqStartOne(id);
          break;
        case "cancel":
          jqCancel(id);
          break;
        case "remove":
          jqRemove(id);
          break;
        default:
          break;
      }
    });
  });
  jqUpdateBadge();
}

function jqAdd(item) {
  jq.items = addItem(jq.items, item);
  const created = jq.items[jq.items.length - 1];
  jqSave();
  jqRender();
  jqExpand();
  return created.id;
}

function jqRemove(id) {
  clearTimer(id);
  jq.items = removeItem(jq.items, id);
  jqSave();
  jqRender();
}

function jqClear() {
  for (const id of Object.keys(jq.timers)) clearTimer(id);
  jq.items = [];
  jqSave();
  jqRender();
}

function jqStartAll() {
  for (const item of startableItems(jq.items)) {
    jqStartOne(item.id);
  }
}

function jqStartOne(id) {
  const item = findItem(jq.items, id);
  if (!item || item.status === "running" || item.status === "starting") return;
  const delayMs = Math.max(0, (Number(item.delay) || 0) * 1000);
  jq.items = updateItem(jq.items, id, {
    status: delayMs > 0 ? "scheduled" : "starting",
    error: null,
  });
  jqSave();
  jqRender();
  schedule(id, delayMs, () => jqStartNow(id));
}

async function jqStartNow(id) {
  clearTimer(id);
  const item = findItem(jq.items, id);
  if (!item) return;
  jq.items = updateItem(jq.items, id, { status: "starting", error: null });
  jqSave();
  jqRender();
  try {
    const data = await api.post(`/api/traffic/${item.kind}`, item.payload);
    jq.items = updateItem(jq.items, id, {
      status: "running",
      job_id: data.job_id,
      error: null,
    });
    jqSave();
    jqRender();
    jqTrack(id);
  } catch (error) {
    jq.items = updateItem(jq.items, id, {
      status: "error",
      error: error.message || "Start failed",
    });
    jqSave();
    jqRender();
  }
}

async function jqTrack(id) {
  clearTimer(id);
  const item = findItem(jq.items, id);
  if (!item || !item.job_id || isTerminal(item)) return;

  try {
    const status = await api.get(
      `/api/traffic/status?job_id=${encodeURIComponent(item.job_id)}`,
    );
    if (status.status === "done") {
      jq.items = updateItem(jq.items, id, {
        status: "done",
        results: status.results || null,
      });
      jqSave();
      jqRender();
      return;
    }
    if (status.status === "error") {
      jq.items = updateItem(jq.items, id, {
        status: "error",
        error: status.error || "Unknown error",
      });
      jqSave();
      jqRender();
      return;
    }
    if (status.status === "cancelled") {
      jq.items = updateItem(jq.items, id, { status: "cancelled" });
      jqSave();
      jqRender();
      return;
    }
    schedule(id, 1000, () => jqTrack(id));
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      jq.items = updateItem(jq.items, id, {
        status: "error",
        error: error.message || "Job not found",
      });
      jqSave();
      jqRender();
      return;
    }
    schedule(id, 1500, () => jqTrack(id));
  }
}

async function jqCancel(id) {
  const item = findItem(jq.items, id);
  if (!item || isTerminal(item)) return;
  clearTimer(id);
  if (item.job_id) {
    try {
      await api.post("/api/traffic/cancel", { job_id: item.job_id });
    } catch (error) {
      jq.items = updateItem(jq.items, id, {
        status: "error",
        error: error.message || "Cancel failed",
      });
      jqSave();
      jqRender();
      return;
    }
  }
  jq.items = updateItem(jq.items, id, { status: "cancelled" });
  jqSave();
  jqRender();
}

function jqPlot(id) {
  const item = findItem(jq.items, id);
  if (!item || !item.results) return;
  if (item.kind === "iperf3") plotIperf3(item);
  else if (item.kind === "ping") plotPing(item);
  else if (item.kind === "hping3") plotHping3(item);
}

function openModal(title, body) {
  const modal = byId("results-modal");
  const titleElement = byId("results-title");
  const bodyElement = byId("results-body");
  if (titleElement) titleElement.textContent = title;
  if (bodyElement) bodyElement.innerHTML = body;
  if (modal) modal.style.display = "flex";
}

function closeResults() {
  const modal = byId("results-modal");
  if (modal) modal.style.display = "none";
}

function plotIperf3(item) {
  const result = item.results;
  const isTcp = (result.protocol || "").toUpperCase() === "TCP";
  const isUdp = !isTcp;

  let metricsHtml = '<div class="results-grid">';
  metricsHtml += metricItem("Protocol", result.protocol);
  metricsHtml += metricItem("Duration", `${fmt(result.duration_seconds)} s`);
  metricsHtml += metricItem("Avg Throughput", `${fmt(result.avg_throughput_mbps)} Mbps`);
  metricsHtml += metricItem("Max Throughput", `${fmt(result.max_throughput_mbps)} Mbps`);
  metricsHtml += metricItem("Min Throughput", `${fmt(result.min_throughput_mbps)} Mbps`);
  if (isTcp) {
    metricsHtml += metricItem("Total Bytes Sent", fmtBytes(result.total_bytes_sent));
    metricsHtml += metricItem(
      "Total Bytes Received",
      fmtBytes(result.total_bytes_received),
    );
    metricsHtml += metricItem("Retransmits", result.total_retransmits);
    metricsHtml += metricItem("Avg RTT", `${fmt(result.avg_rtt_ms)} ms`);
    metricsHtml += metricItem("Max RTT", `${fmt(result.max_rtt_ms)} ms`);
  } else {
    metricsHtml += metricItem("Total Packets", result.total_packets);
    metricsHtml += metricItem("Lost Packets", result.total_lost_packets);
    metricsHtml += metricItem("Avg Loss", `${fmt(result.avg_loss_percent)} %`);
    metricsHtml += metricItem("Avg Jitter", `${fmt(result.avg_jitter_ms)} ms`);
    metricsHtml += metricItem("Out of Order", result.total_out_of_order);
  }
  if (result.pmtu) metricsHtml += metricItem("Path MTU", `${result.pmtu} bytes`);
  metricsHtml += "</div>";

  const chartsHtml =
    '<div class="chart-grid">' +
    '<div class="chart-container"><canvas id="chart-main-1"></canvas></div>' +
    '<div class="chart-container"><canvas id="chart-aux"></canvas></div>' +
    '<div class="chart-container"><canvas id="chart-main-2"></canvas></div>' +
    '<div class="chart-container"><canvas id="chart-cum"></canvas></div>' +
    (isTcp
      ? '<div class="chart-container"><canvas id="chart-tput-tcp"></canvas></div>'
      : "") +
    "</div>";

  openModal(
    `iperf3 Results - ${item.payload.src} -> ${item.payload.dst}`,
    metricsHtml + chartsHtml,
  );

  requestAnimationFrame(() => {
    const intervals = Array.isArray(result.intervals) ? result.intervals : [];
    const streamCount = intervals.reduce(
      (max, entry) =>
        Math.max(max, Array.isArray(entry.streams) ? entry.streams.length : 0),
      0,
    );
    const flowColors = [
      "#ef4444",
      "#22c55e",
      "#eab308",
      "#a78bfa",
      "#f472b6",
      "#60a5fa",
      "#f97316",
      "#84cc16",
    ];

    const times = [];
    const throughput = [];
    const cumulativeBits = [];
    const cwnd = [];
    const rtt = [];
    const aux = [];
    const jitter = [];
    const perThroughput = Array.from({ length: streamCount }, () => []);
    const perCwnd = Array.from({ length: streamCount }, () => []);
    const perRtt = Array.from({ length: streamCount }, () => []);
    const perJitter = Array.from({ length: streamCount }, () => []);
    const perAux = Array.from({ length: streamCount }, () => []);

    let cumulative = 0;
    let elapsed = 0;

    intervals.forEach((entry) => {
      const sum = entry.sum || {};
      const bitsPerSecond = sum.bits_per_second || 0;
      const bytes = sum.bytes || 0;
      let delta = Number(
        sum.seconds != null
          ? sum.seconds
          : sum.end != null && sum.start != null
            ? sum.end - sum.start
            : 1,
      );
      if (!Number.isFinite(delta) || delta <= 0) delta = 1;
      elapsed += delta;
      cumulative += (bytes || 0) * 8;
      times.push(elapsed);
      throughput.push(bitsPerSecond / 1e6);
      cumulativeBits.push(cumulative / 1e6);

      if (isTcp) {
        const stream = (entry.streams && entry.streams[0]) || {};
        cwnd.push(stream.snd_cwnd != null ? stream.snd_cwnd / 1024.0 : null);
        rtt.push(stream.rtt != null ? stream.rtt / 1000.0 : null);
        aux.push(stream.retransmits != null ? stream.retransmits : 0);
        for (let index = 0; index < streamCount; index += 1) {
          const itemStream = (entry.streams && entry.streams[index]) || {};
          perThroughput[index].push(
            itemStream.bits_per_second != null
              ? itemStream.bits_per_second / 1e6
              : null,
          );
          perCwnd[index].push(
            itemStream.snd_cwnd != null ? itemStream.snd_cwnd / 1024.0 : null,
          );
          perRtt[index].push(
            itemStream.rtt != null ? itemStream.rtt / 1000.0 : null,
          );
          perAux[index].push(
            itemStream.retransmits != null ? itemStream.retransmits : null,
          );
        }
      } else {
        let loss = null;
        if (sum.lost_percent != null) loss = Number(sum.lost_percent);
        else if (sum.lost_packets != null && Number(sum.packets) > 0) {
          loss = (Number(sum.lost_packets) / Number(sum.packets)) * 100;
        } else {
          const first = (entry.streams && entry.streams[0]) || {};
          if (first.lost_percent != null) loss = Number(first.lost_percent);
          else if (first.lost_packets != null && Number(first.packets) > 0) {
            loss = (Number(first.lost_packets) / Number(first.packets)) * 100;
          } else loss = 0;
        }
        aux.push(loss);
        for (let index = 0; index < streamCount; index += 1) {
          const itemStream = (entry.streams && entry.streams[index]) || {};
          perThroughput[index].push(
            itemStream.bits_per_second != null
              ? itemStream.bits_per_second / 1e6
              : null,
          );
          perJitter[index].push(
            itemStream.jitter_ms != null ? itemStream.jitter_ms : null,
          );
          let lostPercent = null;
          if (itemStream.lost_percent != null) {
            lostPercent = Number(itemStream.lost_percent);
          } else if (
            itemStream.lost_packets != null &&
            Number(itemStream.packets) > 0
          ) {
            lostPercent =
              (Number(itemStream.lost_packets) / Number(itemStream.packets)) * 100;
          }
          perAux[index].push(lostPercent);
        }
        let jitterMs = sum.jitter_ms;
        if (jitterMs == null) {
          const first = (entry.streams && entry.streams[0]) || {};
          jitterMs = first.jitter_ms;
        }
        let value = Number(jitterMs || 0);
        if (!Number.isFinite(value) || value <= 0) value = 0.001;
        jitter.push(value);
      }
    });

    function formatTick(value) {
      const parsed = parseFloat(value);
      return Number.isFinite(parsed) ? parsed.toFixed(2) : value;
    }

    function flowDatasets(values, prefix) {
      return values.map((series, index) => ({
        label: `${prefix} ${index + 1}`,
        data: series,
        borderColor: flowColors[index % flowColors.length],
        tension: 0.2,
        borderDash: [6, 4],
        pointRadius: 0,
      }));
    }

    const axesPrimary = {
      responsive: true,
      animation: false,
      scales: {
        x: {
          title: { display: true, text: "Time (s)" },
          grid: { color: "#1e2937" },
          ticks: { callback: formatTick },
        },
        y: {
          beginAtZero: true,
          title: { display: true, text: isTcp ? "KB" : "Mbps" },
          grid: { color: "#1e2937" },
        },
      },
      plugins: { legend: { display: true } },
    };
    const axesAux = {
      responsive: true,
      animation: false,
      scales: {
        x: {
          title: { display: true, text: "Time (s)" },
          grid: { color: "#1e2937" },
          ticks: { callback: formatTick },
        },
        y: {
          beginAtZero: true,
          title: { display: true, text: isUdp ? "%" : "Count" },
          grid: { color: "#1e2937" },
        },
      },
      plugins: { legend: { display: true } },
    };
    const axesRtt = {
      responsive: true,
      animation: false,
      scales: {
        x: {
          title: { display: true, text: "Time (s)" },
          grid: { color: "#1e2937" },
          ticks: { callback: formatTick },
        },
        y: {
          beginAtZero: true,
          title: { display: true, text: "ms" },
          grid: { color: "#1e2937" },
        },
      },
      plugins: { legend: { display: true } },
    };
    const axesCumulative = {
      responsive: true,
      animation: false,
      scales: {
        x: {
          title: { display: true, text: "Time (s)" },
          grid: { color: "#1e2937" },
          ticks: { callback: formatTick },
        },
        y: {
          beginAtZero: true,
          title: { display: true, text: "Mbit" },
          grid: { color: "#1e2937" },
        },
      },
      plugins: { legend: { display: true } },
    };
    const axesJitter = {
      responsive: true,
      animation: false,
      scales: {
        x: {
          title: { display: true, text: "Time (s)" },
          grid: { color: "#1e2937" },
          ticks: { callback: formatTick },
        },
        y: {
          type: "logarithmic",
          title: { display: true, text: "Jitter (ms, log)" },
          grid: { color: "#1e2937" },
        },
      },
      plugins: { legend: { display: true } },
    };
    const axesThroughput = {
      responsive: true,
      animation: false,
      scales: {
        x: {
          title: { display: true, text: "Time (s)" },
          grid: { color: "#1e2937" },
          ticks: { callback: formatTick },
        },
        y: {
          beginAtZero: true,
          title: { display: true, text: "Mbps" },
          grid: { color: "#1e2937" },
        },
      },
      plugins: { legend: { display: true } },
    };

    const mainChart = byId("chart-main-1");
    if (mainChart && window.Chart) {
      const base = isTcp
        ? { label: "CWND (KB)", data: cwnd, borderColor: "#3da9fc", tension: 0.2 }
        : {
            label: "Throughput (Mbps)",
            data: throughput,
            borderColor: "#3da9fc",
            tension: 0.2,
          };
      const overlays = isTcp
        ? flowDatasets(perCwnd, "Flow CWND")
        : flowDatasets(perThroughput, "Flow Mbps");
      new Chart(mainChart, {
        type: "line",
        data: {
          labels: times,
          datasets: [base].concat(streamCount > 1 ? overlays : []),
        },
        options: axesPrimary,
      });
    }

    const auxChart = byId("chart-aux");
    if (auxChart && window.Chart) {
      const overlays = flowDatasets(
        perAux,
        isUdp ? "Flow Loss %" : "Flow Retrans",
      );
      new Chart(auxChart, {
        type: "line",
        data: {
          labels: times,
          datasets: [
            {
              label: isUdp ? "Loss %" : "Retrans",
              data: aux,
              borderColor: "#f59e0b",
              tension: 0.2,
            },
          ].concat(streamCount > 1 ? overlays : []),
        },
        options: axesAux,
      });
    }

    const secondaryChart = byId("chart-main-2");
    if (secondaryChart && window.Chart) {
      if (isTcp) {
        const overlays = flowDatasets(perRtt, "Flow RTT");
        new Chart(secondaryChart, {
          type: "line",
          data: {
            labels: times,
            datasets: [
              {
                label: "RTT (ms)",
                data: rtt,
                borderColor: "#10b981",
                tension: 0.2,
              },
            ].concat(streamCount > 1 ? overlays : []),
          },
          options: axesRtt,
        });
      } else {
        const overlays = flowDatasets(perJitter, "Flow Jitter");
        new Chart(secondaryChart, {
          type: "line",
          data: {
            labels: times,
            datasets: [
              {
                label: "Jitter (ms)",
                data: jitter,
                borderColor: "#22c55e",
                tension: 0.2,
              },
            ].concat(streamCount > 1 ? overlays : []),
          },
          options: axesJitter,
        });
      }
    }

    const cumulativeChart = byId("chart-cum");
    if (cumulativeChart && window.Chart) {
      new Chart(cumulativeChart, {
        type: "line",
        data: {
          labels: times,
          datasets: [
            {
              label: "Cumulative Bits (Mbit)",
              data: cumulativeBits,
              borderColor: "#a78bfa",
              tension: 0.2,
            },
          ],
        },
        options: axesCumulative,
      });
    }

    if (isTcp) {
      const throughputChart = byId("chart-tput-tcp");
      if (throughputChart && window.Chart) {
        const overlays = flowDatasets(perThroughput, "Flow Mbps");
        new Chart(throughputChart, {
          type: "line",
          data: {
            labels: times,
            datasets: [
              {
                label: "Throughput (Mbps)",
                data: throughput,
                borderColor: "#3da9fc",
                tension: 0.2,
              },
            ].concat(streamCount > 1 ? overlays : []),
          },
          options: axesThroughput,
        });
      }
    }
  });
}

function plotPing(item) {
  const result = item.results;
  let html = '<div class="results-grid">';
  html += metricItem(
    "Packets",
    `${result.packets_received} / ${result.packets_transmitted}`,
  );
  html += metricItem("Loss", `${fmt(result.packet_loss_percent)} %`);
  html += metricItem("Reachable", result.reachable ? "Yes" : "No");
  html += metricItem("RTT min", `${fmt(result.rtt_min_ms)} ms`);
  html += metricItem("RTT avg", `${fmt(result.rtt_avg_ms)} ms`);
  html += metricItem("RTT max", `${fmt(result.rtt_max_ms)} ms`);
  html += metricItem("RTT mdev", `${fmt(result.rtt_mdev_ms)} ms`);
  html += "</div>";
  openModal(
    `Ping Results - ${item.payload.src} -> ${item.payload.dst}`,
    html,
  );
}

function plotHping3(item) {
  const result = item.results;
  let metricsHtml = '<div class="results-grid">';
  metricsHtml += metricItem(
    "Packets",
    `${result.packets_received} / ${result.packets_transmitted}`,
  );
  metricsHtml += metricItem("Loss", `${fmt(result.packet_loss_percent)} %`);
  metricsHtml += metricItem("Reachable", result.reachable ? "Yes" : "No");
  metricsHtml += metricItem("RTT min", `${fmt(result.rtt_min_ms)} ms`);
  metricsHtml += metricItem("RTT avg", `${fmt(result.rtt_avg_ms)} ms`);
  metricsHtml += metricItem("RTT max", `${fmt(result.rtt_max_ms)} ms`);
  metricsHtml += "</div>";

  const chartsHtml =
    '<div class="chart-grid">' +
    '<div class="chart-container"><canvas id="chart-hping-rtt"></canvas></div>' +
    '<div class="chart-container"><canvas id="chart-hping-cum"></canvas></div>' +
    "</div>";
  openModal(
    `hping3 Results - ${item.payload.src} -> ${item.payload.dst}`,
    metricsHtml + chartsHtml,
  );

  requestAnimationFrame(() => {
    const labels = (result.seq || []).map(String);
    newChart("chart-hping-rtt", "line", labels, [
      {
        label: "RTT (ms)",
        data: result.rtt_ms || [],
        borderColor: "#3da9fc",
        tension: 0.2,
        pointRadius: 2,
      },
    ]);
    newChart("chart-hping-cum", "line", labels, [
      {
        label: "Cumulative Mbit",
        data: result.cumulative_mbit || [],
        borderColor: "#22c55e",
        tension: 0.2,
        pointRadius: 2,
      },
    ]);
  });
}

function newChart(canvasId, type, labels, datasets) {
  const canvas = byId(canvasId);
  if (!canvas || !window.Chart) return null;
  return new Chart(canvas, {
    type,
    data: { labels, datasets },
    options: {
      responsive: true,
      animation: false,
      plugins: { legend: { display: true } },
      scales: {
        x: { title: { display: true, text: "Time (s)" }, grid: { color: "#1e2937" } },
        y: { grid: { color: "#1e2937" } },
      },
    },
  });
}

function metricItem(label, value) {
  return `<div class="result-metric"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd></div>`;
}

function fmt(value) {
  if (value === null || value === undefined || value !== value) return "-";
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(2) : String(value);
}

function fmtBytes(bytes) {
  if (bytes === null || bytes === undefined) return "-";
  const number = Number(bytes);
  if (!Number.isFinite(number)) return "-";
  if (number >= 1e9) return `${(number / 1e9).toFixed(2)} GB`;
  if (number >= 1e6) return `${(number / 1e6).toFixed(2)} MB`;
  if (number >= 1e3) return `${(number / 1e3).toFixed(2)} KB`;
  return `${number} B`;
}

queueInit();

export { jqAdd, jqStartOne };
