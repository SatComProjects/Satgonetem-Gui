/** Space Security Lab UI controller. */
import { api } from "./api.js";
import { escapeHtml } from "./escape.js";
import {
  buildDdosPlan,
  buildFloodFlow,
  buildIperf3Flow,
  buildMitigationPolicy,
  buildPolicyPayload,
  buildSpoofFlow,
  summarizeDdos,
  throughputPoints,
} from "./security_model.js";

const state = {
  range: null,
  captures: [],
  activeUnit: "recon",
  ddosRun: null,
  ddosChart: null,
  captureTimer: null,
  activeCaptureId: null,
  reconLink: null,
  reconTargetDetail: null,
  ddosMitigation: null,
  telemetry: null,
  telemetryTimer: null,
  honeypot: null,
};

function byId(id) {
  return document.getElementById(id);
}

function setMessage(text, isError = false) {
  const element = byId("sec-msg");
  if (!element) return;
  element.textContent = text;
  element.style.color = isError ? "var(--bad)" : "var(--muted)";
}

function fmt(value, fallback = "-") {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function fmtCapacity(kbps) {
  const value = Number(kbps);
  if (!Number.isFinite(value) || value <= 0) return "-";
  if (value >= 1000) return `${(value / 1000).toFixed(1)} Mbps`;
  return `${value} Kbps`;
}

function fmtBytes(value) {
  const bytes = Number(value) || 0;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function setBadge(id, ok, okText, badText) {
  const element = byId(id);
  if (!element) return;
  element.textContent = ok ? okText : badText;
  element.classList.toggle("ok", Boolean(ok));
  element.classList.toggle("bad", !ok);
}

function renderReadiness(range) {
  const readiness = range?.readiness || {};
  setBadge(
    "sec-ready-project",
    readiness.project_loaded,
    "Project: loaded",
    "Project: not loaded",
  );
  setBadge(
    "sec-ready-containers",
    readiness.gonetem_is_on,
    "Containers: running",
    "Containers: stopped",
  );
  setBadge(
    "sec-ready-addressing",
    readiness.addressing_applied,
    "Addressing: applied",
    "Addressing: not applied",
  );
  setBadge(
    "sec-ready-routing",
    readiness.routing_initiated,
    `Routing: ${readiness.routing_method || "applied"}`,
    "Routing: not applied",
  );
  const name = byId("sec-project-name");
  if (name) name.textContent = range?.project_name ? `Project: ${range.project_name}` : "";
  const methodSelect = byId("res-method");
  if (methodSelect && readiness.routing_method) {
    const exists = [...methodSelect.options].some(
      (option) => option.value === readiness.routing_method,
    );
    if (exists) methodSelect.value = readiness.routing_method;
  }
}

function nodeOptions(nodes) {
  return (nodes || []).map((node) => ({
    value: node.name,
    label: node.label || node.name,
  }));
}

function fillSelect(id, options, preferred) {
  const select = byId(id);
  if (!select) return;
  const current = preferred ?? select.value;
  select.replaceChildren();
  for (const option of options) {
    const element = document.createElement("option");
    element.value = option.value;
    element.textContent = option.label;
    select.appendChild(element);
  }
  if (current && options.some((option) => option.value === current)) {
    select.value = current;
  }
}

function renderRecon(range) {
  const links = range?.links || [];
  const nodes = range?.nodes || [];
  const body = byId("recon-links-body");
  if (body) {
    body.replaceChildren();
    if (links.length === 0) {
      const row = document.createElement("tr");
      row.innerHTML = '<td colspan="5" class="muted">No links. Load a project first.</td>';
      body.appendChild(row);
    } else {
      const sorted = [...links].sort((a, b) => {
        const capacityA = Number(a.capacity_kbps) || 0;
        const capacityB = Number(b.capacity_kbps) || 0;
        return capacityA - capacityB;
      });
      for (const link of sorted) {
        const row = document.createElement("tr");
        row.dataset.key = link.key;
        row.tabIndex = 0;
        row.classList.toggle("selected", state.reconLink?.key === link.key);
        row.innerHTML =
          `<td title="${escapeHtml(link.key)}">${escapeHtml(link.src)} → ${escapeHtml(link.dst)}</td>` +
          `<td>${escapeHtml(shortLinkType(link.type))}</td>` +
          `<td>${escapeHtml(fmtCapacity(link.capacity_kbps))}</td>` +
          `<td>${escapeHtml(fmt(link.delay_ms))} ms</td>` +
          `<td>${escapeHtml(link.state || "-")}</td>`;
        body.appendChild(row);
      }
    }
  }

  const stats = byId("recon-stats");
  if (stats) {
    const capacities = links
      .map((link) => Number(link.capacity_kbps) || 0)
      .filter((value) => value > 0);
    const minCapacity = capacities.length ? Math.min(...capacities) : null;
    const bottlenecks = minCapacity
      ? links.filter((link) => Number(link.capacity_kbps) === minCapacity).length
      : 0;
    const types = new Set(links.map((link) => link.type));
    stats.innerHTML =
      `<dl class="sec-stat"><dt>Links</dt><dd>${links.length}</dd></dl>` +
      `<dl class="sec-stat"><dt>Addressable targets</dt><dd>${nodes.length}</dd></dl>` +
      `<dl class="sec-stat"><dt>Link types</dt><dd>${types.size}</dd></dl>` +
      `<dl class="sec-stat"><dt>Lowest-capacity links</dt><dd>${bottlenecks}</dd></dl>`;
  }

  if (state.reconLink) {
    const selected = links.find((link) => link.key === state.reconLink.key);
    renderLinkDetail(selected || null);
  }
}

function renderTargetSelects(range) {
  const nodes = nodeOptions(range?.nodes);
  fillSelect("recon-target", nodes);
  for (const id of ["ddos-src", "ddos-dst", "ddos-attacker", "ddos-target"]) {
    fillSelect(id, nodes);
  }
  for (const id of ["trust-attacker", "trust-target", "trust-spoof"]) {
    fillSelect(id, nodes);
  }
  const resNodes = (range?.nodes || []).map((node) => ({
    value: node.name,
    label: node.label || node.name,
  }));
  fillSelect("res-node", resNodes);
  if (nodes.length > 1) {
    const dst = byId("ddos-dst");
    if (dst && dst.value === nodes[0].value) dst.value = nodes[1].value;
    const attacker = byId("ddos-attacker");
    if (attacker) attacker.value = nodes[nodes.length - 1].value;
    const target = byId("ddos-target");
    if (target) target.value = nodes[1].value;
    const trustAttacker = byId("trust-attacker");
    if (trustAttacker) trustAttacker.value = nodes[nodes.length - 1].value;
    const trustTarget = byId("trust-target");
    if (trustTarget) trustTarget.value = nodes[1].value;
    const spoof = byId("trust-spoof");
    if (spoof) spoof.value = nodes[0].value;
  }
}

function renderLinkSelect(range) {
  const options = (range?.links || []).map((link) => ({
    value: link.key,
    label: `${link.src} → ${link.dst} (${shortLinkType(link.type)})`,
  }));
  fillSelect("res-link", options);
}

function shortLinkType(type) {
  return String(type || "").replace("Link", "");
}

function renderLinkDetail(link) {
  const element = byId("recon-link-detail");
  const button = byId("recon-add-link");
  state.reconLink = link;
  if (button) button.disabled = !link;
  if (!element) return;
  if (!link) {
    element.innerHTML = '<span class="muted">Click a link row to inspect it.</span>';
    return;
  }
  element.innerHTML =
    `<strong>${escapeHtml(link.src)} → ${escapeHtml(link.dst)}</strong><br>` +
    `${escapeHtml(link.type)} · ${escapeHtml(fmtCapacity(link.capacity_kbps))} · ` +
    `${escapeHtml(fmt(link.delay_ms))} ms · ${escapeHtml(link.state || "unknown")}<br>` +
    `<span class="muted">${escapeHtml(link.key)}</span>`;
}

function selectReconLink(key) {
  const link = (state.range?.links || []).find((item) => item.key === key);
  if (!link) return;
  renderLinkDetail(link);
  for (const row of document.querySelectorAll("#recon-links-body tr[data-key]")) {
    row.classList.toggle("selected", row.dataset.key === key);
  }
}

function appendLinkEvidence() {
  const link = state.reconLink;
  const field = byId("recon-evidence");
  if (!link || !field) return;
  const line =
    `- Link ${link.src} -> ${link.dst} (${link.type}): ` +
    `${fmtCapacity(link.capacity_kbps)}, ${fmt(link.delay_ms)} ms, ${link.state}`;
  field.value = field.value ? `${field.value}\n${line}` : line;
}

function renderReconTarget(node) {
  const view = byId("recon-target-detail");
  if (!view) return;
  const loopback = node.loopback?.ipv4 || "-";
  const interfaces = Array.isArray(node.interfaces) ? node.interfaces : [];
  let html =
    `<div class="sec-detail-list">` +
    `<div><dt>Name</dt><dd>${escapeHtml(node.name)}</dd></div>` +
    `<div><dt>Type</dt><dd>${escapeHtml(node.type)}</dd></div>` +
    `<div><dt>Loopback</dt><dd>${escapeHtml(loopback)}</dd></div>` +
    `</div>`;
  html += "<h5>Interfaces</h5>";
  if (interfaces.length === 0) {
    html += '<span class="muted">No interfaces.</span>';
  } else {
    html +=
      '<table class="sec-table"><thead><tr><th>Name</th><th>Dev</th><th>IPv4</th><th>State</th><th>Peer</th></tr></thead><tbody>';
    for (const iface of interfaces) {
      html +=
        `<tr><td>${escapeHtml(iface.name)}</td><td>${escapeHtml(iface.iname)}</td>` +
        `<td>${escapeHtml(iface.ipv4 || "-")}</td>` +
        `<td>${iface.is_active ? "active" : "inactive"}</td>` +
        `<td>${escapeHtml(iface.peer_name || "-")}</td></tr>`;
    }
    html += "</tbody></table>";
  }
  html +=
    "<h5>Routing table</h5>" +
    `<pre class="sec-route">${escapeHtml(routeText(node.routing_table))}</pre>`;
  view.innerHTML = html;
}

async function loadReconTarget() {
  const name = byId("recon-target")?.value;
  const view = byId("recon-target-detail");
  state.reconTargetDetail = null;
  if (!view) return;
  if (!name) {
    view.innerHTML =
      '<span class="muted">Select a target to inspect its interfaces and routes.</span>';
    return;
  }
  view.innerHTML = '<span class="muted">Loading target details...</span>';
  try {
    const data = await api.get(`/api/nodes/${encodeURIComponent(name)}`);
    if (byId("recon-target")?.value !== name) return;
    state.reconTargetDetail = data?.node || null;
    renderReconTarget(data.node);
  } catch (error) {
    if (byId("recon-target")?.value !== name) return;
    view.innerHTML = `<span class="muted">${escapeHtml(error.message || "Could not load target details.")}</span>`;
  }
}

function renderCaptures(captures) {
  state.captures = captures || [];
  const containers = [byId("conf-captures"), byId("trust-evidence")];
  for (const container of containers) {
    if (!container) continue;
    container.replaceChildren();
    if (state.captures.length === 0) {
      const empty = document.createElement("span");
      empty.className = "muted";
      empty.textContent = "No captures yet.";
      container.appendChild(empty);
      continue;
    }
    for (const capture of state.captures) {
      const row = document.createElement("div");
      row.className = "sec-capture";
      const status = capture.status || "unknown";
      const link = capture.download_url
        ? `<a href="${escapeHtml(capture.download_url)}" download>${escapeHtml(capture.id)}.pcap</a>`
        : `<span class="muted">${escapeHtml(capture.id)} (${escapeHtml(status)})</span>`;
      row.innerHTML =
        `<span>${escapeHtml(capture.node)} / ${escapeHtml(capture.interface)}</span>` +
        `<span class="muted">${escapeHtml(status)} · ${fmtBytes(capture.size_bytes)}</span>` +
        '<span class="spacer"></span>' +
        link;
      container.appendChild(row);
    }
  }
}

function renderRange(range) {
  state.range = range;
  renderReadiness(range);
  renderRecon(range);
  renderTargetSelects(range);
  renderLinkSelect(range);
  renderCaptures(range.captures || []);
  if (range?.readiness?.project_loaded) {
    void loadReconTarget();
    setMessage("Range loaded. Start with the reconnaissance mission.");
  } else {
    setMessage("No project loaded. Create or load a project to begin.");
  }
}

async function loadRange() {
  try {
    const range = await api.get("/api/security/range");
    renderRange(range);
  } catch (error) {
    setMessage(error.message || "Could not load the security range.", true);
  }
}

function activateUnit(unit) {
  state.activeUnit = unit;
  for (const button of document.querySelectorAll(".sec-unit-button[data-unit]")) {
    button.classList.toggle("active", button.dataset.unit === unit);
  }
  for (const panel of document.querySelectorAll(".sec-panel[data-panel]")) {
    panel.classList.toggle("active", panel.dataset.panel === unit);
  }
  setTelemetryPolling(unit === "telemetry");
}

function exportNotes() {
  const range = state.range || {};
  const links = range.links || [];
  const target = byId("recon-target")?.value || "(not selected)";
  const concern = byId("recon-concern")?.value || "-";
  const why = byId("recon-why")?.value || "(not written)";
  const impact = byId("recon-impact")?.value || "(not written)";
  const evidence = byId("recon-evidence")?.value || "(no evidence)";
  const selected = state.reconLink;
  const detail = state.reconTargetDetail;
  const lines = [
    "# SatSec reconnaissance dossier",
    "",
    `Project: ${range.project_name || "(none)"}`,
    `Target: ${target}`,
    `Primary concern: ${concern}`,
    "",
    "## Why this target",
    why,
    "",
    "## Expected impact",
    impact,
    "",
    "## Evidence and likely path",
    evidence,
  ];

  if (selected) {
    lines.push(
      "",
      "## Selected link",
      `- ${selected.src} -> ${selected.dst} (${selected.type})`,
      `- Capacity: ${fmtCapacity(selected.capacity_kbps)}`,
      `- Delay: ${fmt(selected.delay_ms)} ms`,
      `- State: ${selected.state}`,
      `- Key: ${selected.key}`,
    );
  }

  if (detail) {
    lines.push(
      "",
      "## Target details",
      `- Name: ${detail.name}`,
      `- Type: ${detail.type}`,
      `- Loopback: ${detail.loopback?.ipv4 || "-"}`,
      "",
      "### Interfaces",
      ...(detail.interfaces || []).map(
        (iface) =>
          `- ${iface.name} (${iface.iname}): ${iface.ipv4 || "-"}, ${iface.is_active ? "active" : "inactive"}, peer ${iface.peer_name || "-"}`,
      ),
      "",
      "### Routing table",
      "```",
      routeText(detail.routing_table),
      "```",
    );
  }

  lines.push(
    "",
    "## Lowest-capacity links",
    ...links
      .slice()
      .sort((a, b) => (Number(a.capacity_kbps) || 0) - (Number(b.capacity_kbps) || 0))
      .slice(0, 10)
      .map(
        (link) =>
          `- ${link.src} -> ${link.dst} (${link.type}): ${fmtCapacity(link.capacity_kbps)}, ${link.delay_ms} ms`,
      ),
  );

  const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "satsec-recon.md";
  anchor.click();
  URL.revokeObjectURL(url);
}

function appendDdosLog(line) {
  const log = byId("ddos-log");
  if (!log) return;
  const stamp = new Date().toLocaleTimeString();
  log.textContent += `[${stamp}] ${line}\n`;
  log.scrollTop = log.scrollHeight;
}

function setDdosStatus(text, isError = false) {
  const element = byId("ddos-status");
  if (!element) return;
  element.textContent = text;
  element.style.color = isError ? "var(--bad)" : "var(--muted)";
}

function setDdosRunning(running) {
  const runButton = byId("ddos-run");
  if (runButton) runButton.disabled = running;
  const stop = byId("ddos-stop");
  if (stop) stop.disabled = !running;
  const mitigate = byId("ddos-mitigate");
  if (mitigate) mitigate.disabled = !running;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function pollTrafficJob(jobId, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const data = await api.get(
      `/api/traffic/status?job_id=${encodeURIComponent(jobId)}`,
    );
    if (["done", "error", "cancelled"].includes(data.status)) return data;
    await sleep(400);
  }
  throw new Error("Traffic job timed out.");
}

async function cancelTrafficJob(jobId) {
  if (!jobId) return;
  try {
    await api.post("/api/traffic/cancel", { job_id: jobId });
  } catch {
    /* already finished or cancelled */
  }
}

function renderDdosMetrics(summary) {
  const element = byId("ddos-metrics");
  if (!element) return;
  const baseline =
    summary.baseline === null ? "-" : `${summary.baseline.toFixed(2)} Mbps`;
  const attack =
    summary.attack === null ? "-" : `${summary.attack.toFixed(2)} Mbps`;
  const drop =
    summary.dropPercent === null ? "-" : `${summary.dropPercent.toFixed(1)}%`;
  element.innerHTML =
    `<dl class="sec-metric"><dt>Baseline</dt><dd>${baseline}</dd></dl>` +
    `<dl class="sec-metric"><dt>During attack</dt><dd>${attack}</dd></dl>` +
    `<dl class="sec-metric"><dt>Throughput drop</dt><dd>${drop}</dd></dl>`;
}

function renderDdosChart(points, attackStart) {
  const canvas = byId("ddos-chart");
  if (!canvas || !window.Chart) return;
  if (state.ddosChart) {
    state.ddosChart.destroy();
    state.ddosChart = null;
  }
  const labels = points.map((point) => point.t.toFixed(0));
  const baseline = points.map((point) =>
    point.t < attackStart ? point.mbps : null,
  );
  const attack = points.map((point) =>
    point.t >= attackStart ? point.mbps : null,
  );
  state.ddosChart = new window.Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Baseline",
          data: baseline,
          borderColor: "#3da9fc",
          backgroundColor: "rgba(61,169,252,0.12)",
          tension: 0.2,
          spanGaps: true,
        },
        {
          label: "Attack window",
          data: attack,
          borderColor: "#f87171",
          backgroundColor: "rgba(248,113,113,0.12)",
          tension: 0.2,
          spanGaps: true,
        },
      ],
    },
    options: {
      responsive: true,
      animation: false,
      maintainAspectRatio: false,
      scales: {
        x: {
          title: { display: true, text: "Time (s)" },
          grid: { color: "#1e2937" },
        },
        y: {
          title: { display: true, text: "Throughput (Mbps)" },
          grid: { color: "#1e2937" },
          beginAtZero: true,
        },
      },
    },
  });
}

function toggleDdosOptions() {
  const rate = byId("ddos-rate")?.value;
  const ppsWrap = byId("ddos-pps-wrap");
  if (ppsWrap) ppsWrap.style.display = rate === "interval" ? "flex" : "none";
  const protocol = byId("ddos-protocol")?.value;
  const flagsWrap = byId("ddos-flags-wrap");
  if (flagsWrap) flagsWrap.style.display = protocol === "tcp" ? "flex" : "none";
  const port = byId("ddos-port");
  if (port) port.disabled = protocol === "icmp";
}

async function runDdos() {
  const src = byId("ddos-src")?.value;
  const dst = byId("ddos-dst")?.value;
  const attacker = byId("ddos-attacker")?.value;
  const target = byId("ddos-target")?.value;
  if (!src || !dst || !attacker || !target) {
    setDdosStatus("Select legitimate and attack endpoints.", true);
    return;
  }
  if (attacker === target) {
    setDdosStatus("Attacker and attack target must be different nodes.", true);
    return;
  }
  if (state.ddosMitigation) {
    await clearDdosMitigation(true);
  }

  const protocol = byId("ddos-protocol")?.value || "udp";
  const rate = byId("ddos-rate")?.value || "flood";
  const pps = byId("ddos-pps")?.value || 5000;
  const size = byId("ddos-size")?.value || 0;
  const dport = byId("ddos-port")?.value || 5201;
  const flags = byId("ddos-flags")?.value || "S";
  const plan = buildDdosPlan({
    baselineSec: byId("ddos-baseline")?.value,
    attackSec: byId("ddos-duration")?.value,
    protocol,
    rate,
  });
  const run = { stop: false, iperfJob: null, attackJob: null };
  state.ddosRun = run;
  setDdosRunning(true);
  setDdosStatus("Starting baseline...");
  const log = byId("ddos-log");
  if (log) log.textContent = "";
  appendDdosLog(
    `baseline ${src} -> ${dst}, ${plan.baselineSec}s TCP; attack starts at ${plan.attackStart}s`,
  );

  try {
    const baseline = await api.post(
      "/api/traffic/iperf3",
      buildIperf3Flow({ src, dst, duration: plan.baselineSec }),
    );
    run.iperfJob = baseline.job_id;
    appendDdosLog(`iperf3 job ${run.iperfJob} started`);
    const baselinePromise = pollTrafficJob(
      run.iperfJob,
      (plan.baselineSec + 20) * 1000,
    ).catch((error) => ({ status: "error", error: error.message }));

    await sleep(plan.attackStart * 1000);
    if (run.stop) {
      await cancelTrafficJob(run.iperfJob);
      setDdosStatus("Stopped.");
      return;
    }

    const attack = await api.post(
      "/api/traffic/hping3",
      buildFloodFlow({
        src: attacker,
        dst: target,
        protocol,
        rate,
        pps,
        size,
        dport,
        flags,
      }),
    );
    run.attackJob = attack.job_id;
    const rateLabel =
      rate === "interval" ? `${pps} packets/sec` : `--${rate === "flood" ? "flood" : rate}`;
    appendDdosLog(
      `${protocol.toUpperCase()} flood ${attacker} -> ${target} started ` +
        `(${rateLabel}, payload ${size} B, port ${protocol === "icmp" ? "-" : dport})`,
    );

    await sleep(plan.attackSec * 1000);
    await cancelTrafficJob(run.attackJob);
    appendDdosLog("attack stopped; waiting for baseline result");
    run.attackJob = null;

    const baselineResult = await baselinePromise;
    if (baselineResult.status === "done" && baselineResult.results) {
      const points = throughputPoints(baselineResult.results.intervals);
      const summary = summarizeDdos(points, plan.attackStart);
      renderDdosChart(points, plan.attackStart);
      renderDdosMetrics(summary);
      if (summary.dropPercent === null) {
        setDdosStatus(
          "Baseline finished, but no interval throughput was reported.",
          true,
        );
      } else {
        setDdosStatus(
          `Baseline ${summary.baseline.toFixed(2)} Mbps, attack ${summary.attack.toFixed(2)} Mbps, drop ${summary.dropPercent.toFixed(1)}%.`,
        );
      }
      appendDdosLog("baseline complete");
    } else if (baselineResult.status === "cancelled") {
      setDdosStatus("Baseline was cancelled.");
    } else {
      setDdosStatus(
        baselineResult.error ||
          "Baseline failed. Check that both nodes are addressable.",
        true,
      );
    }
  } catch (error) {
    if (run.stop) {
      setDdosStatus("Stopped.");
    } else {
      setDdosStatus(error.message || "DDoS lab failed.", true);
      appendDdosLog(error.message || "DDoS lab failed.");
    }
  } finally {
    await cancelTrafficJob(run.attackJob);
    await cancelTrafficJob(run.iperfJob);
    state.ddosRun = null;
    setDdosRunning(false);
  }
}

async function stopDdos() {
  const run = state.ddosRun;
  if (!run) return;
  run.stop = true;
  setDdosStatus("Stopping...");
  await cancelTrafficJob(run.attackJob);
  await cancelTrafficJob(run.iperfJob);
}

function setResStatus(text, isError = false) {
  const element = byId("res-status");
  if (!element) return;
  element.textContent = text;
  element.style.color = isError ? "var(--bad)" : "var(--muted)";
}

function routeText(rows) {
  if (!Array.isArray(rows) || rows.length === 0) return "(empty)";
  return rows.join("\n");
}

function diffRoute(before, after) {
  const beforeRows = Array.isArray(before) ? before : [];
  const afterRows = Array.isArray(after) ? after : [];
  const beforeSet = new Set(beforeRows);
  const afterSet = new Set(afterRows);
  const removed = beforeRows.filter((row) => !afterSet.has(row));
  const added = afterRows.filter((row) => !beforeSet.has(row));
  if (removed.length === 0 && added.length === 0) return "(no route change)";
  return [
    ...removed.map((row) => `- ${row}`),
    ...added.map((row) => `+ ${row}`),
  ].join("\n");
}

function renderRouteViews(before, after) {
  const beforeElement = byId("res-route-before");
  const afterElement = byId("res-route-after");
  const diffElement = byId("res-diff");
  if (beforeElement) beforeElement.textContent = routeText(before);
  if (afterElement) afterElement.textContent = after === null ? "-" : routeText(after);
  if (diffElement) {
    diffElement.textContent = after === null ? "-" : diffRoute(before, after);
  }
}

async function fetchRouteTable(node) {
  if (!node) return [];
  const data = await api.get(`/api/nodes/${encodeURIComponent(node)}`);
  return data?.node?.routing_table || [];
}

async function loadAllNodes() {
  try {
    const nodes = await api.get("/api/nodes");
    const options = (nodes || [])
      .map((node) => ({
        value: node.name,
        label: `${node.name} (${node.type})`,
        type: node.type,
      }))
      .sort((a, b) => (a.type === "satellite" ? 0 : 1) - (b.type === "satellite" ? 0 : 1));
    fillSelect("res-node", options);
    fillSelect("conf-node", options);
    fillSelect("policy-node", options);
    const honeypotOptions = [...options].sort(
      (a, b) => (a.type === "ground_station" ? 0 : 1) - (b.type === "ground_station" ? 0 : 1),
    );
    fillSelect("honeypot-node", honeypotOptions);
    if (state.range?.readiness?.project_loaded) {
      await refreshResRoute();
    }
    await loadConfInterfaces();
    await loadPolicyInterfaces();
    if (state.range?.readiness?.project_loaded) {
      await refreshPolicyStatus();
    }
  } catch {
    /* no project yet */
  }
}

async function loadConfInterfaces() {
  const node = byId("conf-node")?.value;
  const select = byId("conf-interface");
  if (!select) return;
  select.replaceChildren();
  if (!node) return;
  try {
    const data = await api.get(`/api/nodes/${encodeURIComponent(node)}`);
    const interfaces = data?.node?.interfaces || [];
    for (const iface of interfaces) {
      const option = document.createElement("option");
      option.value = iface.iname || iface.name;
      option.textContent = `${iface.iname || iface.name} (${iface.ipv4 || "-"})`;
      select.appendChild(option);
    }
    setConfStatus(
      interfaces.length ? "Select a capture limit and start." : "Node has no interfaces.",
      interfaces.length === 0,
    );
  } catch (error) {
    setConfStatus(error.message || "Could not load interfaces.", true);
  }
}

function setConfStatus(text, isError = false) {
  const element = byId("conf-status");
  if (!element) return;
  element.textContent = text;
  element.style.color = isError ? "var(--bad)" : "var(--muted)";
}

function setConfRunning(running) {
  const start = byId("conf-start");
  if (start) start.disabled = running;
  const stop = byId("conf-stop");
  if (stop) stop.disabled = !running;
}

function startCapturePolling() {
  if (state.captureTimer) clearInterval(state.captureTimer);
  state.captureTimer = setInterval(refreshCaptures, 1500);
}

function stopCapturePolling() {
  if (state.captureTimer) {
    clearInterval(state.captureTimer);
    state.captureTimer = null;
  }
}

async function refreshCaptures() {
  try {
    const captures = await api.get("/api/security/captures");
    renderCaptures(captures);
    if (state.activeCaptureId) {
      const active = captures.find(
        (capture) => capture.id === state.activeCaptureId,
      );
      if (!active || active.status !== "capturing") {
        state.activeCaptureId = null;
        setConfRunning(false);
        stopCapturePolling();
        if (active?.status === "ready") {
          setConfStatus(`Capture ${active.id} ready (${fmtBytes(active.size_bytes)}).`);
        } else if (active?.status === "error") {
          setConfStatus("Capture failed. Check the node image and permissions.", true);
        }
      }
    }
  } catch (error) {
    setConfStatus(error.message || "Could not refresh captures.", true);
  }
}

async function startConfCapture() {
  const node = byId("conf-node")?.value;
  const iface = byId("conf-interface")?.value;
  if (!node || !iface) {
    setConfStatus("Select a node and interface.", true);
    return;
  }
  const limit = Number(byId("conf-limit")?.value) || 200;
  const duration = Number(byId("conf-duration")?.value) || 15;
  try {
    setConfStatus("Starting capture...");
    const capture = await api.post("/api/security/captures", {
      node,
      interface: iface,
      packet_limit: limit,
      duration_sec: duration,
    });
    state.activeCaptureId = capture.id;
    setConfRunning(true);
    setConfStatus(
      `Capturing ${limit} packets or ${duration}s on ${node}/${iface}...`,
    );
    startCapturePolling();
    await refreshCaptures();
  } catch (error) {
    setConfStatus(error.message || "Could not start capture.", true);
  }
}

async function stopConfCapture() {
  if (!state.activeCaptureId) return;
  const captureId = state.activeCaptureId;
  try {
    await api.post(
      `/api/security/captures/${encodeURIComponent(captureId)}/stop`,
    );
    setConfStatus("Stopping capture...");
    await refreshCaptures();
  } catch (error) {
    setConfStatus(error.message || "Could not stop capture.", true);
  }
}

async function refreshResRoute() {
  const node = byId("res-node")?.value;
  try {
    const rows = await fetchRouteTable(node);
    renderRouteViews(rows, null);
    setResStatus(`Loaded route table for ${node || "node"}.`);
  } catch (error) {
    setResStatus(error.message || "Could not read the route table.", true);
  }
}

async function failSelectedLink() {
  const key = byId("res-link")?.value;
  const node = byId("res-node")?.value;
  if (!key) {
    setResStatus("Select a link first.", true);
    return;
  }
  let before = [];
  try {
    before = await fetchRouteTable(node);
    renderRouteViews(before, null);
    setResStatus("Failing link...");
    await api.post(`/api/security/links/${encodeURIComponent(key)}/fail`);
    await loadRange();
    const after = await fetchRouteTable(node);
    renderRouteViews(before, after);
    setResStatus("Link failed. Compare the route diff; Reset restores the snapshot.");
  } catch (error) {
    setResStatus(error.message || "Could not fail the link.", true);
  }
}

async function applyResRouting() {
  const method = byId("res-method")?.value || "static";
  try {
    setResStatus(`Applying ${method}...`);
    await api.post("/api/routing/apply", { method });
    await loadRange();
    await refreshResRoute();
    setResStatus(`Routing method ${method} applied.`);
  } catch (error) {
    setResStatus(error.message || "Could not apply routing.", true);
  }
}

async function resetSecurityRange() {
  try {
    setResStatus("Resetting the range. Containers may restart...");
    await api.post("/api/security/reset");
    await loadRange();
    renderRouteViews([], null);
    await refreshResRoute();
    setResStatus("Range restored from the security snapshot.");
  } catch (error) {
    setResStatus(error.message || "Could not reset the range.", true);
  }
}

async function waitForProjectLoaded(timeoutMs = 120000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const status = await api.get("/api/project/status");
    if (status.state === "loaded") return status;
    if (status.state === "error") {
      throw new Error(status.error || "The range project failed to build.");
    }
    await sleep(1000);
  }
  throw new Error("Timed out waiting for the range project to build.");
}

async function loadSatSecRange() {
  const button = byId("recon-load-range");
  if (button) button.disabled = true;
  setMessage("Building the SatSec range project...");
  try {
    const preset = await api.get("/api/security/preset");
    await api.post("/api/project/create", preset);
    const status = await waitForProjectLoaded();
    await loadRange();
    await loadAllNodes();
    await refreshTrustIp();
    setMessage(
      `SatSec range loaded as ${status.project_name || "SatSecRange"}. Start containers and apply routing from the dashboard.`,
    );
  } catch (error) {
    setMessage(error.message || "Could not load the SatSec range.", true);
  } finally {
    if (button) button.disabled = false;
  }
}

async function resolveNodeIp(name) {
  if (!name) return "";
  const data = await api.get(`/api/nodes/${encodeURIComponent(name)}`);
  const node = data?.node || {};
  if (node.loopback?.ipv4) return node.loopback.ipv4;
  const iface = (node.interfaces || []).find((item) => item.ipv4);
  return iface?.ipv4 || "";
}

async function refreshTrustIp() {
  const name = byId("trust-spoof")?.value;
  const element = byId("trust-ip");
  if (!element) return;
  if (!name) {
    element.textContent = "Spoofed source IP: -";
    return;
  }
  try {
    const ip = await resolveNodeIp(name);
    element.textContent = `Spoofed source IP: ${ip || "(no address found)"}`;
  } catch {
    element.textContent = "Spoofed source IP: -";
  }
}

function setTrustStatus(text, isError = false) {
  const element = byId("trust-status");
  if (!element) return;
  element.textContent = text;
  element.style.color = isError ? "var(--bad)" : "var(--muted)";
}

function setTrustRunning(running) {
  const run = byId("trust-run");
  if (run) run.disabled = running;
  const stop = byId("trust-stop");
  if (stop) stop.disabled = !running;
}

function renderTrustResult(result) {
  const element = byId("trust-result");
  if (!element) return;
  if (!result || result.status !== "done" || !result.results) {
    element.textContent =
      result?.error || `hping3 status: ${result?.status || "unknown"}`;
    return;
  }
  const data = result.results;
  element.textContent = [
    `packets received: ${data.packets_received ?? "-"} / ${data.packets_transmitted ?? "-"}`,
    `packet loss: ${data.packet_loss_percent ?? "-"}%`,
    `reachable: ${data.reachable ? "yes" : "no"}`,
    `rtt avg: ${data.rtt_avg_ms ?? "-"} ms`,
  ].join("\n");
}

async function waitForCaptureReady(captureId, timeoutMs = 12000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const captures = await api.get("/api/security/captures");
    const capture = captures.find((item) => item.id === captureId);
    if (capture && capture.status !== "capturing") return capture;
    await sleep(500);
  }
  return null;
}

async function runTrustTest() {
  const attacker = byId("trust-attacker")?.value;
  const target = byId("trust-target")?.value;
  const spoof = byId("trust-spoof")?.value;
  const flags = byId("trust-flags")?.value || "S";
  const count = Number(byId("trust-count")?.value) || 20;
  const captureEnabled = byId("trust-capture")?.value === "yes";

  if (!attacker || !target || !spoof) {
    setTrustStatus("Select attacker, target, and spoofed source.", true);
    return;
  }
  if (attacker === target) {
    setTrustStatus("Attacker and target must differ.", true);
    return;
  }
  if (spoof === attacker) {
    setTrustStatus("Spoofed source must differ from the attacker.", true);
    return;
  }

  setTrustRunning(true);
  state.trustJobId = null;
  state.trustCaptureId = null;
  try {
    const spoofIp = await resolveNodeIp(spoof);
    if (!spoofIp) {
      setTrustStatus("The spoofed source has no IPv4 address.", true);
      return;
    }
    setTrustStatus(`Spoofing ${spoofIp} toward ${target}...`);
    if (captureEnabled) {
      const detail = await api.get(`/api/nodes/${encodeURIComponent(target)}`);
      const iface =
        detail?.node?.interfaces?.[0]?.iname ||
        detail?.node?.interfaces?.[0]?.name;
      if (!iface) throw new Error("Target has no capture interface.");
      const capture = await api.post("/api/security/captures", {
        node: target,
        interface: iface,
        packet_limit: 100,
        duration_sec: 12,
      });
      state.trustCaptureId = capture.id;
      setTrustStatus(`Capturing on ${target}/${iface} while sending SYN packets...`);
    }

    const job = await api.post(
      "/api/traffic/hping3",
      buildSpoofFlow({
        src: attacker,
        dst: target,
        spoofSrc: spoofIp,
        count,
        flags,
      }),
    );
    state.trustJobId = job.job_id;
    const result = await pollTrafficJob(job.job_id, 20000);
    renderTrustResult(result);
    setTrustStatus(
      result.status === "done"
        ? "Spoofed packets sent. Check the capture evidence."
        : result.error || `hping3 finished as ${result.status}.`,
      result.status !== "done",
    );
  } catch (error) {
    setTrustStatus(error.message || "Spoofing test failed.", true);
  } finally {
    if (state.trustCaptureId) {
      try {
        await api.post(
          `/api/security/captures/${encodeURIComponent(state.trustCaptureId)}/stop`,
        );
        await waitForCaptureReady(state.trustCaptureId);
        await refreshCaptures();
      } catch {
        /* capture may already be complete */
      }
      state.trustCaptureId = null;
    }
    state.trustJobId = null;
    setTrustRunning(false);
  }
}

async function stopTrustTest() {
  setTrustStatus("Stopping spoofing test...");
  if (state.trustJobId) {
    await cancelTrafficJob(state.trustJobId);
  }
  if (state.trustCaptureId) {
    try {
      await api.post(
        `/api/security/captures/${encodeURIComponent(state.trustCaptureId)}/stop`,
      );
      await waitForCaptureReady(state.trustCaptureId);
      await refreshCaptures();
    } catch {
      /* ignore */
    }
    state.trustCaptureId = null;
  }
  setTrustRunning(false);
}


function setPolicyStatus(text, isError = false) {
  const element = byId("policy-status");
  if (!element) return;
  element.textContent = text;
  element.style.color = isError ? "var(--bad)" : "var(--muted)";
}

function renderPolicyPlan(plan) {
  const planElement = byId("policy-plan");
  if (planElement) {
    planElement.textContent = (plan.commands || []).join("\n") || "No commands.";
  }
  const warnings = byId("policy-warnings");
  if (warnings) {
    warnings.textContent = (plan.warnings || []).join("\n");
  }
}

function renderPolicyStatus(status) {
  const body = byId("policy-rules-body");
  if (body) {
    body.replaceChildren();
    const rules = status?.rules || [];
    if (rules.length === 0) {
      body.innerHTML = '<tr><td colspan="5" class="muted">No applied rules.</td></tr>';
    } else {
      for (const rule of rules) {
        const row = document.createElement("tr");
        row.innerHTML =
          `<td>${escapeHtml(rule.chain || "-")}</td>` +
          `<td>${escapeHtml(rule.rule || "-")}</td>` +
          `<td>${escapeHtml(rule.packets ?? 0)}</td>` +
          `<td>${escapeHtml(rule.bytes ?? 0)}</td>` +
          `<td>${escapeHtml(rule.target || "-")}</td>`;
        body.appendChild(row);
      }
    }
  }
  if (status?.applied) {
    setPolicyStatus(
      `Policy applied on ${status.node} (${status.family}); ${status.rules.length} counter rows.`,
    );
  } else {
    setPolicyStatus("No managed policy chain on this node.");
  }
}

function policyFields() {
  return {
    node: byId("policy-node")?.value,
    family: byId("policy-family")?.value,
    preset: byId("policy-preset")?.value,
    defaultInbound: byId("policy-default")?.value,
    allowEstablished: byId("policy-established")?.checked,
    allowIcmp: byId("policy-icmp")?.checked,
    allowLoopback: byId("policy-loopback")?.checked,
    managementSources: byId("policy-management-sources")?.value,
    managementPorts: byId("policy-management-ports")?.value,
    managementProtocol: byId("policy-management-proto")?.value,
    ttcSources: byId("policy-ttc-sources")?.value,
    ttcPorts: byId("policy-ttc-ports")?.value,
    ttcProtocol: byId("policy-ttc-proto")?.value,
    telemetrySources: byId("policy-telemetry-sources")?.value,
    telemetryPorts: byId("policy-telemetry-ports")?.value,
    telemetryProtocol: byId("policy-telemetry-proto")?.value,
    bcp38: byId("policy-bcp38")?.checked,
    bcp38Egress: byId("policy-bcp38-egress")?.value,
    rateEnabled: byId("policy-rate-enabled")?.checked,
    rateProtocol: byId("policy-rate-proto")?.value,
    ratePort: byId("policy-rate-port")?.value,
    rateSource: byId("policy-rate-source")?.value,
    ratePps: byId("policy-rate-pps")?.value,
    rateBurst: byId("policy-rate-burst")?.value,
    rateSyn: byId("policy-rate-syn")?.checked,
    connEnabled: byId("policy-conn-enabled")?.checked,
    connPort: byId("policy-conn-port")?.value,
    connSource: byId("policy-conn-source")?.value,
    connMax: byId("policy-conn-max")?.value,
    ingressEnabled: byId("policy-ingress-enabled")?.checked,
    ingressInterface: byId("policy-interface")?.value,
    ingressProtocol: byId("policy-ingress-proto")?.value,
    ingressPort: byId("policy-ingress-port")?.value,
    ingressRate: byId("policy-ingress-rate")?.value,
    ingressBurst: byId("policy-ingress-burst")?.value,
    dscpEnabled: byId("policy-dscp-enabled")?.checked,
    dscpProtocol: byId("policy-dscp-proto")?.value,
    dscpPort: byId("policy-dscp-port")?.value,
    dscp: byId("policy-dscp")?.value,
  };
}

function policyPayload() {
  const fields = policyFields();
  if (!fields.node) throw new Error("Select a policy node.");
  return buildPolicyPayload(fields);
}

async function previewPolicy() {
  try {
    const payload = policyPayload();
    setPolicyStatus("Building preview...");
    const plan = await api.post("/api/security/policies/preview", payload);
    renderPolicyPlan(plan);
    setPolicyStatus(`Preview ready: ${plan.commands.length} commands.`);
  } catch (error) {
    setPolicyStatus(error.message || "Preview failed.", true);
  }
}

async function applyPolicy() {
  try {
    const payload = policyPayload();
    setPolicyStatus("Applying policy...");
    const status = await api.post("/api/security/policies", payload);
    renderPolicyStatus(status);
    setPolicyStatus(`Policy applied on ${status.node}.`);
  } catch (error) {
    setPolicyStatus(error.message || "Policy apply failed.", true);
  }
}

async function clearPolicy() {
  const node = byId("policy-node")?.value;
  if (!node) {
    setPolicyStatus("Select a policy node.", true);
    return;
  }
  try {
    setPolicyStatus("Clearing policy...");
    await api.post(`/api/security/policies/${encodeURIComponent(node)}/clear`);
    renderPolicyStatus({ applied: false, node, family: "ipv4", rules: [], qos: [] });
    setPolicyStatus(`Policy cleared on ${node}.`);
  } catch (error) {
    setPolicyStatus(error.message || "Policy clear failed.", true);
  }
}

async function refreshPolicyStatus() {
  const node = byId("policy-node")?.value;
  if (!node) return;
  try {
    const status = await api.get(`/api/security/policies/${encodeURIComponent(node)}`);
    renderPolicyStatus(status);
  } catch (error) {
    if (error.status === 404) {
      renderPolicyStatus({ applied: false, node, family: "ipv4", rules: [], qos: [] });
      setPolicyStatus("Node is not running; preview still works.", true);
    } else {
      setPolicyStatus(error.message || "Could not read policy status.", true);
    }
  }
}

async function loadPolicyInterfaces() {
  const node = byId("policy-node")?.value;
  const select = byId("policy-interface");
  if (!select) return;
  select.replaceChildren();
  if (!node) return;
  try {
    const data = await api.get(`/api/nodes/${encodeURIComponent(node)}`);
    const interfaces = data?.node?.interfaces || [];
    for (const iface of interfaces) {
      const option = document.createElement("option");
      option.value = iface.iname || iface.name;
      option.textContent = `${iface.iname || iface.name} (${iface.ipv4 || "-"})`;
      select.appendChild(option);
    }
  } catch {
    /* node details are unavailable before the project is loaded */
  }
}

function applyPolicyPreset() {
  const preset = byId("policy-preset")?.value;
  const set = (id, value) => {
    const element = byId(id);
    if (element) element.value = value;
  };
  const check = (id, value) => {
    const element = byId(id);
    if (element) element.checked = value;
  };
  if (preset === "default-deny") {
    set("policy-default", "drop");
    check("policy-established", true);
    check("policy-icmp", false);
  } else if (preset === "ttc-only") {
    set("policy-default", "drop");
    check("policy-established", true);
    check("policy-icmp", false);
    set("policy-ttc-ports", "5201");
    set("policy-telemetry-ports", "5201");
  } else if (preset === "ddos-mitigation") {
    set("policy-default", "accept");
    check("policy-established", true);
    check("policy-icmp", false);
    check("policy-rate-enabled", true);
    check("policy-conn-enabled", true);
    set("policy-rate-proto", "tcp");
    set("policy-rate-port", "5201");
    set("policy-rate-pps", "100");
    set("policy-rate-burst", "200");
    set("policy-conn-port", "5201");
    set("policy-conn-max", "10");
  }
}

async function applyDdosMitigation() {
  const target = byId("ddos-target")?.value;
  const attacker = byId("ddos-attacker")?.value;
  if (!target || !attacker) {
    setDdosStatus("Select a target and attacker first.", true);
    return;
  }
  if (!state.ddosRun?.attackJob) {
    setDdosStatus("Wait until the attack is running, then apply mitigation.", true);
    return;
  }
  const protocol = byId("ddos-protocol")?.value || "udp";
  const port = Number(byId("ddos-port")?.value) || 5201;
  const flags = byId("ddos-flags")?.value || "S";
  try {
    const attackerIp = await resolveNodeIp(attacker);
    if (!attackerIp) throw new Error("Attacker has no IPv4 address.");
    const policy = buildMitigationPolicy({
      node: target,
      attackerIp,
      protocol,
      port,
      synOnly: protocol === "tcp" && flags.includes("S"),
    });
    const status = await api.post("/api/security/policies", policy);
    state.ddosMitigation = { node: target, policy };
    const clear = byId("ddos-clear-mitigation");
    if (clear) clear.disabled = false;
    setDdosStatus(
      `Mitigation applied to ${target} for ${attackerIp}: 100 pps and 10 connections.`,
    );
    renderPolicyStatus(status);
  } catch (error) {
    setDdosStatus(error.message || "Could not apply DDoS mitigation.", true);
  }
}

async function clearDdosMitigation(silent = false) {
  const mitigation = state.ddosMitigation;
  if (!mitigation) return;
  try {
    await api.post(
      `/api/security/policies/${encodeURIComponent(mitigation.node)}/clear`,
    );
    state.ddosMitigation = null;
    const clear = byId("ddos-clear-mitigation");
    if (clear) clear.disabled = true;
    if (!silent) setDdosStatus(`Mitigation cleared on ${mitigation.node}.`);
  } catch (error) {
    if (!silent) {
      setDdosStatus(error.message || "Could not clear DDoS mitigation.", true);
    }
  }
}


function setTelemetryStatus(text, isError = false) {
  const element = byId("telemetry-status");
  if (!element) return;
  element.textContent = text;
  element.style.color = isError ? "var(--bad)" : "var(--muted)";
}

function renderTelemetryStats(data) {
  const element = byId("telemetry-stats");
  if (!element) return;
  const nodes = data.nodes || [];
  const links = data.links || [];
  const alerts = data.alerts || [];
  element.innerHTML =
    `<dl class="sec-stat"><dt>Baseline samples</dt><dd>${data.baseline_samples ?? 0}</dd></dl>` +
    `<dl class="sec-stat"><dt>Nodes</dt><dd>${nodes.length}</dd></dl>` +
    `<dl class="sec-stat"><dt>Links</dt><dd>${links.length}</dd></dl>` +
    `<dl class="sec-stat"><dt>Alerts</dt><dd>${alerts.length}</dd></dl>`;
}

function renderTelemetryNodes(nodes) {
  const body = byId("telemetry-nodes-body");
  if (!body) return;
  body.replaceChildren();
  if (!nodes || nodes.length === 0) {
    body.innerHTML = '<tr><td colspan="8" class="muted">No node metrics.</td></tr>';
    return;
  }
  for (const node of nodes) {
    const interfaces = node.interfaces || [];
    const rx = interfaces.reduce((sum, item) => sum + Number(item.rx_mbps || 0), 0);
    const tx = interfaces.reduce((sum, item) => sum + Number(item.tx_mbps || 0), 0);
    const drops = interfaces.reduce(
      (sum, item) => sum + Number(item.rx_dropped || 0) + Number(item.tx_dropped || 0),
      0,
    );
    const errors = interfaces.reduce(
      (sum, item) => sum + Number(item.rx_errors || 0) + Number(item.tx_errors || 0),
      0,
    );
    const row = document.createElement("tr");
    row.innerHTML =
      `<td>${escapeHtml(node.name)}</td>` +
      `<td>${escapeHtml(node.type || "-")}</td>` +
      `<td>${escapeHtml(node.route_count ?? 0)}</td>` +
      `<td>${escapeHtml((node.protocols || []).join("; ") || "-")}</td>` +
      `<td>${rx.toFixed(2)} Mbps</td>` +
      `<td>${tx.toFixed(2)} Mbps</td>` +
      `<td>${drops}</td>` +
      `<td>${errors}${node.error ? ` · ${escapeHtml(node.error)}` : ""}</td>`;
    body.appendChild(row);
  }
}

function renderTelemetryLinks(links) {
  const body = byId("telemetry-links-body");
  if (!body) return;
  body.replaceChildren();
  if (!links || links.length === 0) {
    body.innerHTML = '<tr><td colspan="8" class="muted">No link metrics.</td></tr>';
    return;
  }
  for (const link of links) {
    const row = document.createElement("tr");
    const budget = link.budget?.enabled ? "enabled" : "-";
    row.innerHTML =
      `<td>${escapeHtml(link.src)} → ${escapeHtml(link.dst)}</td>` +
      `<td>${escapeHtml(fmtCapacity(link.capacity_kbps))}</td>` +
      `<td>${Number(link.rx_mbps || 0).toFixed(2)} Mbps</td>` +
      `<td>${Number(link.tx_mbps || 0).toFixed(2)} Mbps</td>` +
      `<td>${link.rx_dropped ?? 0}</td>` +
      `<td>${link.rx_errors ?? 0}</td>` +
      `<td>${escapeHtml(link.state || "-")}</td>` +
      `<td>${escapeHtml(budget)}</td>`;
    body.appendChild(row);
  }
}

function renderTelemetryAlerts(alerts) {
  const container = byId("telemetry-alerts");
  if (!container) return;
  container.replaceChildren();
  if (!alerts || alerts.length === 0) {
    const empty = document.createElement("span");
    empty.className = "muted";
    empty.textContent = "No alerts yet.";
    container.appendChild(empty);
    return;
  }
  for (const alert of alerts) {
    const item = document.createElement("div");
    item.className = `sec-alert ${escapeHtml(alert.severity || "info")}`;
    const time = new Date(Number(alert.timestamp) * 1000).toLocaleTimeString();
    item.innerHTML =
      `<span class="severity">${escapeHtml(alert.severity || "info")}</span>` +
      `<span class="time">${escapeHtml(time)}</span>` +
      `<strong>${escapeHtml(alert.node || "range")}</strong>` +
      `<span>${escapeHtml(alert.message || "")}</span>` +
      `<span class="metric">${escapeHtml(alert.metric || "")}</span>`;
    container.appendChild(item);
  }
}

async function refreshTelemetry() {
  try {
    const data = await api.get("/api/security/telemetry");
    state.telemetry = data;
    renderTelemetryStats(data);
    renderTelemetryNodes(data.nodes);
    renderTelemetryLinks(data.links);
    renderTelemetryAlerts(data.alerts);
    setTelemetryStatus(
      `Sampled at ${new Date(data.sampled_at * 1000).toLocaleTimeString()} (${data.interval_seconds.toFixed(1)}s interval).`,
    );
  } catch (error) {
    if (error.status === 404 || error.status === 409) {
      setTelemetryStatus("Start the range containers and apply routing to sample telemetry.", true);
    } else {
      setTelemetryStatus(error.message || "Telemetry sample failed.", true);
    }
  }
}

async function clearTelemetryAlerts() {
  try {
    await api.post("/api/security/telemetry/clear-alerts");
    await refreshTelemetry();
    setTelemetryStatus("Alert history cleared.");
  } catch (error) {
    setTelemetryStatus(error.message || "Could not clear alerts.", true);
  }
}

function setTelemetryPolling(active) {
  if (state.telemetryTimer) {
    clearInterval(state.telemetryTimer);
    state.telemetryTimer = null;
  }
  if (active) {
    refreshTelemetry();
    state.telemetryTimer = setInterval(refreshTelemetry, 5000);
  }
}


function setHoneypotStatus(text, isError = false) {
  const element = byId("honeypot-status");
  if (!element) return;
  element.textContent = text;
  element.style.color = isError ? "var(--bad)" : "var(--muted)";
}

function renderHoneypot(status) {
  state.honeypot = status;
  const stop = byId("honeypot-stop");
  if (stop) stop.disabled = !status?.running;
  const container = byId("honeypot-events");
  if (!container) return;
  container.replaceChildren();
  const events = status?.events || [];
  if (events.length === 0) {
    const empty = document.createElement("span");
    empty.className = "muted";
    empty.textContent = status?.running
      ? "No connections yet."
      : "Start the honeypot to collect connection attempts.";
    container.appendChild(empty);
    return;
  }
  for (const event of events.slice().reverse()) {
    const row = document.createElement("div");
    row.className = "sec-capture";
    const time = new Date(Number(event.timestamp) * 1000).toLocaleTimeString();
    row.innerHTML =
      `<span>${escapeHtml(time)}</span>` +
      `<span>${escapeHtml(event.peer || "unknown")}:${escapeHtml(event.source_port ?? 0)}</span>` +
      '<span class="spacer"></span>' +
      '<span class="muted">decoy SSH connection</span>';
    container.appendChild(row);
  }
}

async function startHoneypot() {
  const node = byId("honeypot-node")?.value;
  const port = Number(byId("honeypot-port")?.value) || 2222;
  if (!node) {
    setHoneypotStatus("Select a honeypot node.", true);
    return;
  }
  try {
    setHoneypotStatus("Starting decoy listener...");
    const status = await api.post("/api/security/honeypots", { node, port });
    renderHoneypot(status);
    setHoneypotStatus(`Honeypot ${status.running ? "running" : "stopped"} on ${node}:${port}.`);
  } catch (error) {
    setHoneypotStatus(error.message || "Could not start honeypot.", true);
  }
}

async function refreshHoneypot() {
  const node = byId("honeypot-node")?.value;
  const port = Number(byId("honeypot-port")?.value) || 2222;
  if (!node) return;
  try {
    const status = await api.get(
      `/api/security/honeypots/${encodeURIComponent(node)}/${port}`,
    );
    renderHoneypot(status);
    setHoneypotStatus(
      status.running
        ? `Listening on ${node}:${port}; ${status.events.length} connections.`
        : "No honeypot running.",
    );
  } catch (error) {
    setHoneypotStatus(error.message || "Could not read honeypot status.", true);
  }
}

async function stopHoneypot() {
  const node = byId("honeypot-node")?.value;
  const port = Number(byId("honeypot-port")?.value) || 2222;
  if (!node) return;
  try {
    await api.post(
      `/api/security/honeypots/${encodeURIComponent(node)}/${port}/stop`,
    );
    setHoneypotStatus("Honeypot stopped.");
    await refreshHoneypot();
  } catch (error) {
    setHoneypotStatus(error.message || "Could not stop honeypot.", true);
  }
}

for (const button of document.querySelectorAll(".sec-unit-button[data-unit]")) {
  button.addEventListener("click", () => activateUnit(button.dataset.unit));
}
byId("sec-refresh")?.addEventListener("click", loadRange);
byId("recon-load-range")?.addEventListener("click", loadSatSecRange);
byId("recon-export")?.addEventListener("click", exportNotes);
byId("recon-target")?.addEventListener("change", loadReconTarget);
byId("recon-add-link")?.addEventListener("click", appendLinkEvidence);
byId("recon-links-body")?.addEventListener("click", (event) => {
  const row = event.target.closest("tr[data-key]");
  if (row) selectReconLink(row.dataset.key);
});
byId("recon-links-body")?.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const row = event.target.closest("tr[data-key]");
  if (!row) return;
  event.preventDefault();
  selectReconLink(row.dataset.key);
});
byId("ddos-run")?.addEventListener("click", runDdos);
byId("ddos-stop")?.addEventListener("click", stopDdos);
byId("ddos-mitigate")?.addEventListener("click", applyDdosMitigation);
byId("ddos-clear-mitigation")?.addEventListener("click", () => clearDdosMitigation());
byId("ddos-rate")?.addEventListener("change", toggleDdosOptions);
byId("ddos-protocol")?.addEventListener("change", toggleDdosOptions);
byId("res-fail")?.addEventListener("click", failSelectedLink);
byId("res-apply")?.addEventListener("click", applyResRouting);
byId("res-reset")?.addEventListener("click", resetSecurityRange);
byId("res-node")?.addEventListener("change", refreshResRoute);
byId("conf-node")?.addEventListener("change", loadConfInterfaces);
byId("conf-start")?.addEventListener("click", startConfCapture);
byId("conf-stop")?.addEventListener("click", stopConfCapture);
byId("trust-spoof")?.addEventListener("change", refreshTrustIp);
byId("trust-run")?.addEventListener("click", runTrustTest);
byId("trust-stop")?.addEventListener("click", stopTrustTest);
byId("policy-preset")?.addEventListener("change", applyPolicyPreset);
byId("policy-preview")?.addEventListener("click", previewPolicy);
byId("policy-apply")?.addEventListener("click", applyPolicy);
byId("policy-clear")?.addEventListener("click", clearPolicy);
byId("policy-refresh")?.addEventListener("click", refreshPolicyStatus);
byId("policy-node")?.addEventListener("change", async () => {
  await loadPolicyInterfaces();
  await refreshPolicyStatus();
});
byId("telemetry-refresh")?.addEventListener("click", refreshTelemetry);
byId("telemetry-clear-alerts")?.addEventListener("click", clearTelemetryAlerts);
byId("honeypot-start")?.addEventListener("click", startHoneypot);
byId("honeypot-stop")?.addEventListener("click", stopHoneypot);
byId("honeypot-refresh")?.addEventListener("click", refreshHoneypot);

toggleDdosOptions();
loadRange().then(loadAllNodes).then(refreshTrustIp);
