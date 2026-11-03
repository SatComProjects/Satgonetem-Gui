/** Node Explorer page controller. */
import { api } from "./api.js";
import { escapeHtml } from "./escape.js";

const POLL_INTERVAL_MS = 5000;
const detailCache = {};

function el(id) {
  return document.getElementById(id);
}

function showMsg(text, isError = false) {
  const message = el("nodes-msg");
  if (!message) return;
  message.textContent = text;
  message.style.color = isError ? "var(--bad)" : "var(--muted)";
}

function buildInterfaceRow(iface) {
  return (
    "<tr>" +
    `<td>${escapeHtml(iface.name)}</td>` +
    `<td>${escapeHtml(iface.iname)}</td>` +
    `<td>${escapeHtml(iface.ipv4 || "-")}</td>` +
    `<td>${escapeHtml(iface.ipv6 || "-")}</td>` +
    `<td>${escapeHtml(iface.type || "-")}</td>` +
    `<td>${iface.is_active ? "Active" : "Inactive"}</td>` +
    `<td>${escapeHtml(iface.peer_name || "-")}</td>` +
    "</tr>"
  );
}

function buildDetailPanel(data) {
  const position = data.position || {};
  const loopback = data.loopback || {};
  let html = '<div class="node-detail">';

  html += '<div class="detail-section"><h4>Position</h4><dl class="detail-dl">';
  for (const [label, value] of [
    ["Latitude", position.latitude],
    ["Longitude", position.longitude],
    ["Altitude", position.altitude],
  ]) {
    html += `<div class="detail-row"><dt>${label}</dt><dd>${escapeHtml(value)}</dd></div>`;
  }
  html += "</dl></div>";

  html += '<div class="detail-section"><h4>Loopback</h4><dl class="detail-dl">';
  for (const [label, value] of [
    ["IPv4", loopback.ipv4],
    ["IPv6", loopback.ipv6],
  ]) {
    html += `<div class="detail-row"><dt>${label}</dt><dd>${escapeHtml(value || "-")}</dd></div>`;
  }
  html += "</dl></div>";

  if (data.type === "satellite") {
    html += '<div class="detail-section"><h4>QoS</h4><dl class="detail-dl">';
    html += `<div class="detail-row"><dt>Default QoS</dt><dd>${data.default_qos_is_on ? "On" : "Off"}</dd></div>`;
    html += `<div class="detail-row"><dt>Program QoS</dt><dd>${data.program_specific_qos_is_on ? "On" : "Off"}</dd></div>`;
    html += "</dl></div>";
  }

  if (data.type === "ground_station" && data.city) {
    html += `<div class="detail-section"><h4>City</h4><p class="muted">${escapeHtml(data.city)}</p></div>`;
  }

  html += '<div class="detail-section"><h4>Interfaces</h4>';
  if (data.interfaces && data.interfaces.length) {
    html +=
      '<table class="iface-table"><thead><tr><th>Name</th><th>Dev</th><th>IPv4</th><th>IPv6</th><th>Type</th><th>State</th><th>Peer</th></tr></thead><tbody>';
    for (const iface of data.interfaces) html += buildInterfaceRow(iface);
    html += "</tbody></table>";
  } else {
    html += '<p class="muted">No interfaces.</p>';
  }
  html += "</div>";

  html += '<div class="detail-section"><h4>Routing Table</h4>';
  if (data.routing_table && data.routing_table.length) {
    html += `<pre class="routing-pre">${escapeHtml(data.routing_table.join("\n"))}</pre>`;
  } else {
    html +=
      '<p class="muted">No routing table available (containers may not be running).</p>';
  }
  html += "</div></div>";
  return html;
}

async function toggleNode(name) {
  const row = el(`row-${name}`);
  const detail = el(`detail-${name}`);
  if (!row || !detail) return;

  const expanded = detail.style.display === "block";
  if (!expanded && !detailCache[name]) {
    detail.innerHTML = '<div class="muted">Loading...</div>';
    detail.style.display = "block";
    row.classList.add("expanded");
    try {
      const data = await api.get(`/api/nodes/${encodeURIComponent(name)}`);
      detailCache[name] = data.node;
      detail.innerHTML = buildDetailPanel(data.node);
    } catch (error) {
      detail.innerHTML = `<div class="muted" style="color:var(--bad)">Error: ${escapeHtml(error.message || error)}</div>`;
    }
    return;
  }

  if (!expanded && detailCache[name]) {
    detail.innerHTML = buildDetailPanel(detailCache[name]);
  }
  detail.style.display = expanded ? "none" : "block";
  row.classList.toggle("expanded", !expanded);
}

function buildNodeRow(node) {
  const name = escapeHtml(node.name);
  let label = name;
  if (node.type === "ground_station" && node.city) {
    label += ` (${escapeHtml(node.city)})`;
  }
  return (
    `<div class="node-row" id="row-${name}" data-node-name="${name}">` +
    '<span class="node-chevron">&#9654;</span>' +
    `<span class="node-label">${label}</span>` +
    "</div>" +
    `<div class="node-detail-wrapper" id="detail-${name}" style="display:none;"></div>`
  );
}

function initNodeList(container) {
  container.addEventListener("click", (event) => {
    const row = event.target.closest(".node-row");
    if (!row || !container.contains(row)) return;
    toggleNode(row.dataset.nodeName);
  });
}

function syncNodeList(container, nodes, emptyMessage) {
  const existing = {};
  let child = container.firstChild;
  while (child) {
    if (child.id && child.id.startsWith("row-")) {
      existing[child.id] = child;
      const detail = el(child.id.replace("row-", "detail-"));
      if (detail) existing[detail.id] = detail;
    }
    child = child.nextSibling;
  }

  const seen = {};
  const fragment = document.createDocumentFragment();
  for (const node of nodes) {
    const rowId = `row-${node.name}`;
    const detailId = `detail-${node.name}`;
    seen[rowId] = true;
    seen[detailId] = true;
    if (!existing[rowId]) {
      const wrapper = document.createElement("div");
      wrapper.innerHTML = buildNodeRow(node);
      while (wrapper.firstChild) fragment.appendChild(wrapper.firstChild);
    }
  }
  if (fragment.childNodes.length) container.appendChild(fragment);

  child = container.firstChild;
  while (child) {
    const next = child.nextSibling;
    if (!child.id || !seen[child.id]) container.removeChild(child);
    child = next;
  }

  let hasRows = false;
  child = container.firstChild;
  while (child) {
    if (child.id && child.id.startsWith("row-")) {
      hasRows = true;
      break;
    }
    child = child.nextSibling;
  }
  if (!hasRows && nodes.length === 0) {
    if (!container.querySelector(":scope > .muted")) {
      const empty = document.createElement("div");
      empty.className = "muted";
      empty.textContent = emptyMessage;
      container.appendChild(empty);
    }
  } else {
    container.querySelector(":scope > .muted")?.remove();
  }
}

function renderNodes(nodes) {
  const satellites = [];
  const stations = [];
  for (const node of nodes) {
    if (node.type === "satellite") satellites.push(node);
    else stations.push(node);
  }
  syncNodeList(el("satellites-list"), satellites, "No satellites.");
  syncNodeList(el("ground-stations-list"), stations, "No ground stations.");
}

async function loadNodes() {
  try {
    const nodes = await api.get("/api/nodes");
    showMsg("");
    renderNodes(Array.isArray(nodes) ? nodes : []);
  } catch (error) {
    showMsg(`Error: ${error.message || error}`, true);
    el("satellites-list").replaceChildren();
    el("ground-stations-list").replaceChildren();
  }
}

initNodeList(el("satellites-list"));
initNodeList(el("ground-stations-list"));
loadNodes();
setInterval(loadNodes, POLL_INTERVAL_MS);
