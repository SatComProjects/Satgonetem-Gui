/** Space Security Lab UI controller. */
import { api } from "./api.js";
import { escapeHtml } from "./escape.js";
import {
  buildDdosPlan,
  buildFloodFlow,
  buildIperf3Flow,
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
      row.innerHTML = '<td colspan="6" class="muted">No links. Load a project first.</td>';
      body.appendChild(row);
    } else {
      const sorted = [...links].sort((a, b) => {
        const capacityA = Number(a.capacity_kbps) || 0;
        const capacityB = Number(b.capacity_kbps) || 0;
        return capacityA - capacityB;
      });
      for (const link of sorted) {
        const row = document.createElement("tr");
        row.innerHTML =
          `<td title="${escapeHtml(link.key)}">${escapeHtml(link.key.slice(0, 36))}</td>` +
          `<td>${escapeHtml(link.src)} → ${escapeHtml(link.dst)}</td>` +
          `<td>${escapeHtml(link.type)}</td>` +
          `<td>${escapeHtml(fmtCapacity(link.capacity_kbps))}</td>` +
          `<td>${escapeHtml(fmt(link.delay_ms))} ms</td>` +
          `<td>${escapeHtml(link.state || "-")}</td>`;
        body.appendChild(row);
      }
    }
  }

  const targets = byId("recon-targets");
  if (targets) {
    targets.replaceChildren();
    if (nodes.length === 0) {
      targets.innerHTML = '<span class="muted">No addressable targets.</span>';
    } else {
      for (const node of nodes) {
        const card = document.createElement("div");
        card.className = "sec-target";
        card.innerHTML = `<strong>${escapeHtml(node.label || node.name)}</strong><br>` +
          `<span class="muted">${escapeHtml(node.type)}</span>`;
        targets.appendChild(card);
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
}

function renderTargetSelects(range) {
  const nodes = nodeOptions(range?.nodes);
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
    const spoof = byId("trust-spoof");
    if (spoof) spoof.value = nodes[0].value;
  }
}

function renderLinkSelect(range) {
  const options = (range?.links || []).map((link) => ({
    value: link.key,
    label: `${link.src} → ${link.dst} (${lockType(link.type)})`,
  }));
  fillSelect("res-link", options);
}

function lockType(type) {
  return String(type || "").replace("Link", "");
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
    setMessage("Range loaded. Reconnaissance is read-only.");
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
}

function exportNotes() {
  const notes = byId("recon-notes")?.value || "";
  const range = state.range || {};
  const links = range.links || [];
  const lines = [
    "# SatSec reconnaissance notes",
    "",
    `Project: ${range.project_name || "(none)"}`,
    `Links: ${links.length}`,
    "",
    "## Notes",
    notes || "(no notes)",
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
  ];
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

  const plan = buildDdosPlan({
    baselineSec: byId("ddos-baseline")?.value,
    attackSec: byId("ddos-duration")?.value,
    protocol: byId("ddos-protocol")?.value,
    rate: byId("ddos-rate")?.value,
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
        protocol: plan.protocol,
        rate: plan.rate,
      }),
    );
    run.attackJob = attack.job_id;
    appendDdosLog(
      `${plan.protocol.toUpperCase()} flood ${attacker} -> ${target} started (${run.attackJob})`,
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
    const options = (nodes || []).map((node) => ({
      value: node.name,
      label: `${node.name} (${node.type})`,
    }));
    fillSelect("res-node", options);
    fillSelect("conf-node", options);
    await loadConfInterfaces();
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

for (const button of document.querySelectorAll(".sec-unit-button[data-unit]")) {
  button.addEventListener("click", () => activateUnit(button.dataset.unit));
}
byId("sec-refresh")?.addEventListener("click", loadRange);
byId("recon-export")?.addEventListener("click", exportNotes);
byId("ddos-run")?.addEventListener("click", runDdos);
byId("ddos-stop")?.addEventListener("click", stopDdos);
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

loadRange().then(loadAllNodes).then(refreshTrustIp);
