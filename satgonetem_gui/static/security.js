/** Space Security Lab UI controller. */
import { api } from "./api.js";
import { escapeHtml } from "./escape.js";

const state = {
  range: null,
  captures: [],
  activeUnit: "recon",
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
  for (const id of ["conf-node", "trust-attacker", "trust-target", "trust-spoof"]) {
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
    if (spoof) spoof.value = nodes[1].value;
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

for (const button of document.querySelectorAll(".sec-unit-button[data-unit]")) {
  button.addEventListener("click", () => activateUnit(button.dataset.unit));
}
byId("sec-refresh")?.addEventListener("click", loadRange);
byId("recon-export")?.addEventListener("click", exportNotes);

loadRange();
