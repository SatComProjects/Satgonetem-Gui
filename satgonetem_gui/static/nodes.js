/** Node Explorer page controller. */
import { api } from "./api.js?v=4";
import { escapeHtml } from "./escape.js";
import {
  FAVORITES_KEY,
  cacheEntry,
  filterNodes,
  isFresh,
  nodeCountText,
  normalizeFavorites,
  sortNodes,
  staleCacheKeys,
  toggleFavorite,
} from "./nodes_model.js?v=3";
import {
  formatCapacityKbps,
  formatLinkDelay,
  linkDirectionLabel,
  linkPeer,
  linkStateLabel,
  linkTypeLabel,
  linksForNode,
} from "./links_model.js?v=1";
import {
  formatDistance,
  pathChain,
  pathRows,
  pathSummary,
} from "./path_model.js?v=1";

const POLL_INTERVAL_MS = 5000;
const detailCache = new Map();
let topologyLinks = [];
let allNodes = [];
let favorites = loadFavorites();
let searchTimer = null;
let lastPathData = null;
let pathBusy = false;
let pathSelectsEnabled = false;
let pathNodesSignature = "";

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
    `<td>${escapeHtml(iface.type || "-")}</td>` +
    `<td>${iface.is_active ? "Active" : "Inactive"}</td>` +
    `<td>${escapeHtml(iface.peer_name || "-")}</td>` +
    "</tr>"
  );
}

function buildDetailPanel(data, links = []) {
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
  for (const [label, value] of [["IPv4", loopback.ipv4]]) {
    html += `<div class="detail-row"><dt>${label}</dt><dd>${escapeHtml(value || "-")}</dd></div>`;
  }
  html += "</dl></div>";

  if (data.type === "satellite") {
    html += '<div class="detail-section"><h4>QoS</h4><dl class="detail-dl">';
    html += `<div class="detail-row"><dt>Default QoS</dt><dd>${data.default_qos_is_on ? "On" : "Off"}</dd></div>`;
    html += `<div class="detail-row"><dt>Program QoS</dt><dd>${data.program_specific_qos_is_on ? "On" : "Off"}</dd></div>`;
    html += "</dl></div>";

    const addressable = Boolean(data.addressable);
    const safeName = escapeHtml(data.name);
    html += '<div class="detail-section addressability-control">';
    html += "<h4>Traffic</h4>";
    html += `<p class="muted" id="addressability-state-${safeName}">Traffic endpoint: ${addressable ? "Enabled" : "Disabled"}</p>`;
    html +=
      `<button type="button" class="button small addressability-toggle" ` +
      `data-action="toggle-addressable" data-node-name="${safeName}" ` +
      `data-enabled="${addressable}">` +
      `${addressable ? "Disable as traffic endpoint" : "Enable as traffic endpoint"}` +
      "</button>";
    html += "</div>";
  }

  if (data.type === "ground_station" && data.city) {
    html += `<div class="detail-section"><h4>City</h4><p class="muted">${escapeHtml(data.city)}</p></div>`;
  }

  html += '<div class="detail-section"><h4>Interfaces</h4>';
  if (data.interfaces && data.interfaces.length) {
    html +=
      '<table class="iface-table"><thead><tr><th>Name</th><th>Dev</th><th>IPv4</th><th>Type</th><th>State</th><th>Peer</th></tr></thead><tbody>';
    for (const iface of data.interfaces) html += buildInterfaceRow(iface);
    html += "</tbody></table>";
  } else {
    html += '<p class="muted">No interfaces.</p>';
  }
  html += "</div>";

  html += '<div class="detail-section"><h4>Links</h4>';
  const nodeLinks = linksForNode(links, data.name);
  if (nodeLinks.length) {
    html +=
      '<div class="link-table-wrap"><table class="iface-table link-table"><thead><tr>' +
      "<th>Peer</th><th>Type</th><th>Direction</th><th>Distance</th>" +
      "<th>Delay</th><th>Capacity</th><th>State</th>" +
      "</tr></thead><tbody>";
    for (const link of nodeLinks) {
      const inactive = link.is_active === false;
      html +=
        `<tr class="${inactive ? "link-inactive" : ""}">` +
        `<td>${escapeHtml(linkPeer(link, data.name))}</td>` +
        `<td>${escapeHtml(linkTypeLabel(link.type))}</td>` +
        `<td>${escapeHtml(linkDirectionLabel(link))}</td>` +
        `<td>${escapeHtml(formatDistance(link.distance_km))}</td>` +
        `<td>${escapeHtml(formatLinkDelay(link.delay_ms))}</td>` +
        `<td>${escapeHtml(formatCapacityKbps(link.capacity_kbps))}</td>` +
        `<td>${escapeHtml(linkStateLabel(link.is_active))}</td>` +
        "</tr>";
    }
    html += "</tbody></table></div>";
  } else {
    html += '<p class="muted">No links reported.</p>';
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
  const toggle = row.querySelector(".node-toggle");
  const cached = detailCache.get(name);
  if (!expanded && !isFresh(cached)) {
    detail.innerHTML = '<div class="muted">Loading...</div>';
    detail.style.display = "block";
    row.classList.add("expanded");
    toggle?.setAttribute("aria-expanded", "true");
    try {
      const data = await api.get(`/api/nodes/${encodeURIComponent(name)}`);
      detailCache.set(name, cacheEntry(data.node));
      detail.innerHTML = buildDetailPanel(data.node, topologyLinks);
    } catch (error) {
      detailCache.delete(name);
      detail.innerHTML = `<div class="muted" style="color:var(--bad)">Error: ${escapeHtml(error.message || error)}</div>`;
    }
    return;
  }

  if (!expanded && isFresh(cached)) {
    detail.innerHTML = buildDetailPanel(cached.data, topologyLinks);
  }
  detail.style.display = expanded ? "none" : "block";
  row.classList.toggle("expanded", !expanded);
  toggle?.setAttribute("aria-expanded", String(!expanded));
}

function buildNodeRow(node) {
  const name = escapeHtml(node.name);
  const active = favorites.includes(node.name);
  let label = name;
  if (node.type === "ground_station" && node.city) {
    label += ` (${escapeHtml(node.city)})`;
  }
  return (
    `<div class="node-row" id="row-${name}" data-node-name="${name}">` +
    `<button type="button" class="node-toggle" data-action="toggle" aria-expanded="false" aria-controls="detail-${name}">` +
    '<span class="node-chevron">&#9654;</span>' +
    `<span class="node-label">${label}</span>` +
    "</button>" +
    `<button type="button" class="node-fav" data-action="favorite" data-node-name="${name}" aria-pressed="${active}" aria-label="${active ? "Remove" : "Add"} ${name} favorite">${active ? "★" : "☆"}</button>` +
    "</div>" +
    `<div class="node-detail-wrapper" id="detail-${name}" style="display:none;"></div>`
  );
}

function loadFavorites() {
  try {
    return normalizeFavorites(
      JSON.parse(localStorage.getItem(FAVORITES_KEY) || "null"),
    );
  } catch {
    return [];
  }
}

function persistFavorites() {
  try {
    localStorage.setItem(FAVORITES_KEY, JSON.stringify(favorites));
    return true;
  } catch {
    showMsg("Favorites could not be saved in this browser.", true);
    return false;
  }
}

function toggleNodeFavorite(button) {
  const name = button.dataset.nodeName;
  if (!name) return;
  favorites = toggleFavorite(favorites, name);
  if (!persistFavorites()) return;
  const active = favorites.includes(name);
  button.setAttribute("aria-pressed", String(active));
  button.textContent = active ? "★" : "☆";
  button.setAttribute(
    "aria-label",
    `${active ? "Remove" : "Add"} ${name} favorite`,
  );
  if (el("node-favorites-only")?.checked) {
    renderNodes(allNodes, { force: true });
  }
}

async function toggleAddressable(button) {
  const name = button.dataset.nodeName;
  if (!name) return;
  const enabled = button.dataset.enabled !== "true";
  button.disabled = true;
  try {
    const data = await api.post(
      `/api/nodes/${encodeURIComponent(name)}/addressable`,
      { enabled },
    );
    const isEnabled = Boolean(data.addressable);
    button.dataset.enabled = String(isEnabled);
    button.textContent = isEnabled
      ? "Disable as traffic endpoint"
      : "Enable as traffic endpoint";

    const state = el(`addressability-state-${name}`);
    if (state) {
      const text = `Traffic endpoint: ${isEnabled ? "Enabled" : "Disabled"}`;
      state.textContent = data.routing_refresh_required
        ? `${text}. Re-apply addressing and routing.`
        : text;
    }
    detailCache.delete(name);
    showMsg(
      data.routing_refresh_required
        ? "Endpoints updated. Re-apply Addressing & Routing on the Dashboard before running traffic."
        : "Endpoints updated.",
    );
  } catch (error) {
    showMsg(`Error: ${error.message || error}`, true);
  } finally {
    button.disabled = false;
  }
}

function initNodeList(container) {
  container.addEventListener("click", (event) => {
    const favorite = event.target.closest('[data-action="favorite"]');
    if (favorite && container.contains(favorite)) {
      event.preventDefault();
      toggleNodeFavorite(favorite);
      return;
    }
    const toggle = event.target.closest('[data-action="toggle-addressable"]');
    if (!toggle || !container.contains(toggle)) return;
    event.preventDefault();
    toggleAddressable(toggle);
  });
  container.addEventListener("click", (event) => {
    const toggleButton = event.target.closest('[data-action="toggle"]');
    if (toggleButton && container.contains(toggleButton)) {
      const row = toggleButton.closest(".node-row");
      if (row) toggleNode(row.dataset.nodeName);
      return;
    }
    if (event.target.closest("button")) return;
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

function currentFilters() {
  return {
    query: el("node-search")?.value || "",
    type: el("node-type-filter")?.value || "all",
    sort: el("node-sort")?.value || "name",
    favoritesOnly: Boolean(el("node-favorites-only")?.checked),
  };
}

function renderNodes(nodes, { force = false } = {}) {
  allNodes = Array.isArray(nodes) ? nodes : [];
  const filters = currentFilters();
  const filtered = filterNodes(allNodes, {
    query: filters.query,
    type: filters.type,
    favoritesOnly: filters.favoritesOnly,
    favorites,
  });
  const satellites = sortNodes(
    filtered.filter((node) => node.type === "satellite"),
    filters.sort,
  );
  const stations = sortNodes(
    filtered.filter((node) => node.type !== "satellite"),
    filters.sort,
  );
  const satellitesCard = el("card-satellites");
  const stationsCard = el("card-ground-stations");
  if (satellitesCard) satellitesCard.hidden = filters.type === "ground_station";
  if (stationsCard) stationsCard.hidden = filters.type === "satellite";

  for (const name of staleCacheKeys(
    detailCache.keys(),
    allNodes.map((node) => node.name),
  )) {
    detailCache.delete(name);
  }
  if (force) {
    el("satellites-list")?.replaceChildren();
    el("ground-stations-list")?.replaceChildren();
  }
  const filteredView =
    filters.query.trim() || filters.type !== "all" || filters.favoritesOnly;
  syncNodeList(
    el("satellites-list"),
    satellites,
    filteredView ? "No matching satellites." : "No satellites.",
  );
  syncNodeList(
    el("ground-stations-list"),
    stations,
    filteredView ? "No matching ground stations." : "No ground stations.",
  );
  const count = el("node-count");
  if (count) count.textContent = nodeCountText(filtered.length, allNodes.length);
  populatePathSelects(allNodes);
}

function bindNodeFilters() {
  el("node-search")?.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => renderNodes(allNodes, { force: true }), 120);
  });
  el("node-type-filter")?.addEventListener("change", () =>
    renderNodes(allNodes, { force: true }),
  );
  el("node-sort")?.addEventListener("change", () =>
    renderNodes(allNodes, { force: true }),
  );
  el("node-favorites-only")?.addEventListener("change", () =>
    renderNodes(allNodes, { force: true }),
  );
}

function setPathMsg(text, isError = false) {
  const message = el("path-msg");
  if (!message) return;
  message.textContent = text;
  message.style.color = isError ? "var(--bad)" : "var(--muted)";
}

function fillPathSelect(select, nodes) {
  const previous = select.value;
  select.replaceChildren();
  for (const node of nodes) {
    const option = document.createElement("option");
    option.value = node.name;
    option.textContent =
      node.type === "ground_station" && node.city
        ? `${node.name} (${node.city})`
        : node.name;
    select.appendChild(option);
  }
  if (nodes.some((node) => node.name === previous)) {
    select.value = previous;
  }
}

function populatePathSelects(nodes) {
  const source = el("path-src");
  const destination = el("path-dst");
  if (!source || !destination) return;

  const sorted = [...nodes].sort((a, b) =>
    a.name.localeCompare(b.name, undefined, { numeric: true }),
  );
  const signature = sorted
    .map((node) => `${node.name}|${node.city || ""}`)
    .join("\n");
  if (signature === pathNodesSignature) return;
  pathNodesSignature = signature;

  fillPathSelect(source, sorted);
  fillPathSelect(destination, sorted);

  if (!source.value && sorted.length) {
    const ground = sorted.find((node) => node.type === "ground_station");
    source.value = (ground || sorted[0]).name;
  }
  if (!destination.value && sorted.length) {
    const satellite = sorted.find((node) => node.type === "satellite");
    destination.value = (satellite || sorted[1] || sorted[0]).name;
  }

  const enabled = sorted.length >= 2;
  const wasEnabled = pathSelectsEnabled;
  pathSelectsEnabled = enabled;
  source.disabled = !enabled;
  destination.disabled = !enabled;
  const trace = el("path-trace");
  const clear = el("path-clear");
  if (trace) trace.disabled = pathBusy || !enabled;
  if (clear) clear.disabled = pathBusy || !enabled;
  if (!enabled) {
    setPathMsg("Load a project with at least two nodes to trace a path.");
  } else if (!wasEnabled) {
    setPathMsg("");
  }
}

function renderPath(data) {
  lastPathData = data;
  const summary = el("path-summary");
  const wrap = el("path-table-wrap");
  const body = el("path-table-body");
  const actions = el("path-actions");
  if (summary) summary.textContent = pathSummary(data);

  if (!data.found) {
    if (body) body.replaceChildren();
    if (wrap) wrap.hidden = true;
    if (actions) actions.hidden = true;
    setPathMsg(data.note || "No path was found.");
    return;
  }

  if (body) {
    body.innerHTML = pathRows(data)
      .map((row) => {
        const direction = row.direction
          ? ` <span class="path-direction">${escapeHtml(row.direction.toLowerCase())}</span>`
          : "";
        return `
          <tr>
            <td>${row.hop}</td>
            <td>${escapeHtml(row.link)}</td>
            <td>${escapeHtml(row.type)}${direction}</td>
            <td>${escapeHtml(row.distance)}</td>
            <td>${escapeHtml(row.delay)}</td>
            <td>${escapeHtml(row.cumulativeDistance)} / ${escapeHtml(row.cumulativeDelay)}</td>
          </tr>`;
      })
      .join("");
  }
  if (wrap) wrap.hidden = false;
  if (actions) actions.hidden = false;
  setPathMsg(data.note || "");
}

function setPathTraceBusy(busy) {
  pathBusy = busy;
  const trace = el("path-trace");
  const clear = el("path-clear");
  const source = el("path-src");
  const destination = el("path-dst");
  if (trace) {
    trace.disabled = busy || (source?.options.length || 0) < 2;
  }
  if (clear) {
    clear.disabled = busy || (source?.options.length || 0) < 2;
  }
}

async function tracePath(event) {
  event.preventDefault();
  if (pathBusy) return;
  const source = el("path-src")?.value || "";
  const destination = el("path-dst")?.value || "";
  if (!source || !destination) {
    setPathMsg("Choose a source and destination.", true);
    return;
  }
  if (source === destination) {
    setPathMsg("Choose different source and destination nodes.", true);
    return;
  }

  setPathTraceBusy(true);
  setPathMsg("Tracing path...");
  try {
    const data = await api.get(
      `/api/routing/path?src=${encodeURIComponent(source)}&dst=${encodeURIComponent(destination)}`,
    );
    renderPath(data);
  } catch (error) {
    lastPathData = null;
    const summary = el("path-summary");
    if (summary) summary.textContent = "";
    const wrap = el("path-table-wrap");
    if (wrap) wrap.hidden = true;
    const actions = el("path-actions");
    if (actions) actions.hidden = true;
    setPathMsg(error.message || "Could not trace the path.", true);
  } finally {
    setPathTraceBusy(false);
  }
}

function clearPath() {
  lastPathData = null;
  const summary = el("path-summary");
  const wrap = el("path-table-wrap");
  const body = el("path-table-body");
  const actions = el("path-actions");
  if (summary) summary.textContent = "";
  if (body) body.replaceChildren();
  if (wrap) wrap.hidden = true;
  if (actions) actions.hidden = true;
  setPathMsg("");
}

function copyText(text) {
  if (navigator.clipboard?.writeText) {
    return navigator.clipboard.writeText(text);
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  const copied = document.execCommand("copy");
  area.remove();
  return copied
    ? Promise.resolve()
    : Promise.reject(new Error("Clipboard is unavailable."));
}

async function copyPath() {
  if (!lastPathData?.found) return;
  try {
    await copyText(pathChain(lastPathData));
    setPathMsg("Path copied to the clipboard.");
  } catch (error) {
    setPathMsg(error.message || "Could not copy the path.", true);
  }
}

function exportPath() {
  if (!lastPathData) return;
  const blob = new Blob([JSON.stringify(lastPathData, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `path-${lastPathData.src}-${lastPathData.dst}.json`;
  link.style.display = "none";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
  setPathMsg("Path exported as JSON.");
}

function bindPathControls() {
  el("path-form")?.addEventListener("submit", tracePath);
  el("path-clear")?.addEventListener("click", clearPath);
  el("path-copy")?.addEventListener("click", copyPath);
  el("path-export")?.addEventListener("click", exportPath);
}

async function loadNodes() {
  try {
    const nodes = await api.getAll("/api/nodes");
    try {
      const links = await api.getAll("/api/links");
      topologyLinks = Array.isArray(links) ? links : [];
    } catch {
      topologyLinks = [];
    }
    showMsg("");
    renderNodes(Array.isArray(nodes) ? nodes : []);
  } catch (error) {
    showMsg(`Error: ${error.message || error}`, true);
    el("satellites-list").replaceChildren();
    el("ground-stations-list").replaceChildren();
    populatePathSelects([]);
  }
}

bindPathControls();
bindNodeFilters();
initNodeList(el("satellites-list"));
initNodeList(el("ground-stations-list"));
loadNodes();
setInterval(loadNodes, POLL_INTERVAL_MS);
