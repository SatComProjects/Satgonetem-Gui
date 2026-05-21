/**
 * Nodes page controller.
 *
 * Loads all nodes via /api/nodes and renders expandable lists for satellites
 * and ground stations. Clicking a node fetches detailed info via
 * /api/nodes/{name} and reveals it in place.
 */

const POLL_INTERVAL_MS = 5000;

/**
 * @param {string} id
 * @returns {HTMLElement}
 */
function el(id) {
  return document.getElementById(id);
}

/** @type {Object.<string, Object>} */
const detailCache = {};

/**
 * Show a transient message in the page header area.
 *
 * @param {string} text
 * @param {boolean} [isError]
 */
function showMsg(text, isError) {
  var msg = el("nodes-msg");
  msg.textContent = text;
  msg.style.color = isError ? "var(--bad)" : "var(--muted)";
}

/**
 * Build HTML for a single interface row.
 *
 * @param {Object} iface
 * @returns {string}
 */
function buildInterfaceRow(iface) {
  return (
    "<tr>" +
    "<td>" + escapeHtml(iface.name) + "</td>" +
    "<td>" + escapeHtml(iface.iname) + "</td>" +
    "<td>" + escapeHtml(iface.ipv4 || "-") + "</td>" +
    "<td>" + escapeHtml(iface.ipv6 || "-") + "</td>" +
    "<td>" + escapeHtml(iface.type || "-") + "</td>" +
    "<td>" + (iface.is_active ? "Active" : "Inactive") + "</td>" +
    "<td>" + escapeHtml(iface.peer_name || "-") + "</td>" +
    "</tr>"
  );
}

/**
 * Escape HTML special characters.
 *
 * @param {string} text
 * @returns {string}
 */
function escapeHtml(text) {
  if (text == null) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/**
 * Build the detail panel HTML for a node.
 *
 * @param {Object} data
 * @returns {string}
 */
function buildDetailPanel(data) {
  var pos = data.position || {};
  var html = '<div class="node-detail">';

  html += '<div class="detail-section">';
  html += '<h4>Position</h4>';
  html += '<dl class="detail-dl">';
  html += '<div class="detail-row"><dt>Latitude</dt><dd>' + escapeHtml(pos.latitude) + "</dd></div>";
  html += '<div class="detail-row"><dt>Longitude</dt><dd>' + escapeHtml(pos.longitude) + "</dd></div>";
  html += '<div class="detail-row"><dt>Altitude</dt><dd>' + escapeHtml(pos.altitude) + "</dd></div>";
  html += "</dl>";
  html += "</div>";

  html += '<div class="detail-section">';
  html += '<h4>Loopback</h4>';
  html += '<dl class="detail-dl">';
  html += '<div class="detail-row"><dt>IPv4</dt><dd>' + escapeHtml(data.loopback.ipv4 || "-") + "</dd></div>";
  html += '<div class="detail-row"><dt>IPv6</dt><dd>' + escapeHtml(data.loopback.ipv6 || "-") + "</dd></div>";
  html += "</dl>";
  html += "</div>";

  if (data.type === "satellite") {
    html += '<div class="detail-section">';
    html += '<h4>QoS</h4>';
    html += '<dl class="detail-dl">';
    html += '<div class="detail-row"><dt>Default QoS</dt><dd>' + (data.default_qos_is_on ? "On" : "Off") + "</dd></div>";
    html += '<div class="detail-row"><dt>Program QoS</dt><dd>' + (data.program_specific_qos_is_on ? "On" : "Off") + "</dd></div>";
    html += "</dl>";
    html += "</div>";
  }

  if (data.type === "ground_station" && data.city) {
    html += '<div class="detail-section">';
    html += '<h4>City</h4>';
    html += '<p class="muted">' + escapeHtml(data.city) + "</p>";
    html += "</div>";
  }

  html += '<div class="detail-section">';
  html += '<h4>Interfaces</h4>';
  if (data.interfaces && data.interfaces.length) {
    html += '<table class="iface-table"><thead><tr>';
    html += "<th>Name</th><th>Dev</th><th>IPv4</th><th>IPv6</th><th>Type</th><th>State</th><th>Peer</th>";
    html += "</tr></thead><tbody>";
    for (var i = 0; i < data.interfaces.length; i++) {
      html += buildInterfaceRow(data.interfaces[i]);
    }
    html += "</tbody></table>";
  } else {
    html += '<p class="muted">No interfaces.</p>';
  }
  html += "</div>";

  html += '<div class="detail-section">';
  html += '<h4>Routing Table</h4>';
  if (data.routing_table && data.routing_table.length) {
    html += '<pre class="routing-pre">' + escapeHtml(data.routing_table.join("\n")) + "</pre>";
  } else {
    html += '<p class="muted">No routing table available (containers may not be running).</p>';
  }
  html += "</div>";

  html += "</div>";
  return html;
}

/**
 * Toggle the expanded state of a node row.
 *
 * @param {string} name
 */
async function toggleNode(name) {
  var row = el("row-" + name);
  var detail = el("detail-" + name);
  if (!row || !detail) return;

  var isExpanded = detail.style.display === "block";

  if (!isExpanded && !detailCache[name]) {
    detail.innerHTML = '<div class="muted">Loading...</div>';
    detail.style.display = "block";
    row.classList.add("expanded");
    try {
      var r = await fetch("/api/nodes/" + encodeURIComponent(name));
      var j = await r.json().catch(function () { return {}; });
      if (!r.ok || !j.ok) {
        detail.innerHTML = '<div class="muted" style="color:var(--bad)">Error: ' + escapeHtml(j.error || "Unknown error") + "</div>";
        return;
      }
      detailCache[name] = j.node;
      detail.innerHTML = buildDetailPanel(j.node);
    } catch (err) {
      detail.innerHTML = '<div class="muted" style="color:var(--bad)">Error: ' + escapeHtml(String(err.message || err)) + "</div>";
    }
    return;
  }

  if (!isExpanded && detailCache[name]) {
    detail.innerHTML = buildDetailPanel(detailCache[name]);
  }

  detail.style.display = isExpanded ? "none" : "block";
  row.classList.toggle("expanded", !isExpanded);
}

/**
 * Build the HTML for a single node row.
 *
 * @param {Object} node
 * @returns {string}
 */
function buildNodeRow(node) {
  var label = node.name;
  if (node.type === "ground_station" && node.city) {
    label += " (" + escapeHtml(node.city) + ")";
  }
  return (
    '<div class="node-row" id="row-' + escapeHtml(node.name) + '" onclick="toggleNode(\'' + escapeHtml(node.name) + '\')">' +
    '<span class="node-chevron">&#9654;</span>' +
    '<span class="node-label">' + label + "</span>" +
    "</div>" +
    '<div class="node-detail-wrapper" id="detail-' + escapeHtml(node.name) + '" style="display:none;"></div>'
  );
}

/**
 * Sync a container's children with a list of nodes.
 * Existing rows are preserved so expanded state is not lost.
 *
 * @param {HTMLElement} container
 * @param {Array} nodes
 * @param {string} emptyMsg
 */
function syncNodeList(container, nodes, emptyMsg) {
  var existing = {};
  var child = container.firstChild;
  while (child) {
    if (child.id && child.id.startsWith("row-")) {
      existing[child.id] = child;
      var detail = el(child.id.replace("row-", "detail-"));
      if (detail) {
        existing[detail.id] = detail;
      }
    }
    child = child.nextSibling;
  }

  var seen = {};
  var fragment = document.createDocumentFragment();
  for (var i = 0; i < nodes.length; i++) {
    var name = nodes[i].name;
    var rowId = "row-" + name;
    var detailId = "detail-" + name;
    seen[rowId] = true;
    seen[detailId] = true;
    if (!existing[rowId]) {
      var wrapper = document.createElement("div");
      wrapper.innerHTML = buildNodeRow(nodes[i]);
      while (wrapper.firstChild) {
        fragment.appendChild(wrapper.firstChild);
      }
    }
  }
  if (fragment.childNodes.length) {
    container.appendChild(fragment);
  }

  // Remove nodes that are no longer present, and any placeholder text.
  child = container.firstChild;
  while (child) {
    var next = child.nextSibling;
    if (!child.id || !seen[child.id]) {
      container.removeChild(child);
    }
    child = next;
  }

  // Show placeholder only when truly empty.
  var hasRows = false;
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
      container.innerHTML = '<div class="muted">' + emptyMsg + "</div>";
    }
  } else {
    var placeholder = container.querySelector(":scope > .muted");
    if (placeholder) {
      container.removeChild(placeholder);
    }
  }
}

/**
 * Render the full node list into the DOM.
 *
 * @param {Array} nodes
 */
function renderNodes(nodes) {
  var sats = [];
  var gnds = [];
  for (var i = 0; i < nodes.length; i++) {
    if (nodes[i].type === "satellite") {
      sats.push(nodes[i]);
    } else {
      gnds.push(nodes[i]);
    }
  }

  syncNodeList(el("satellites-list"), sats, "No satellites.");
  syncNodeList(el("ground-stations-list"), gnds, "No ground stations.");
}

async function loadNodes() {
  try {
    var r = await fetch("/api/nodes");
    if (!r.ok) {
      var j = await r.json().catch(function () { return {}; });
      showMsg(j.error || ("HTTP " + r.status), true);
      el("satellites-list").innerHTML = "";
      el("ground-stations-list").innerHTML = "";
      return;
    }
    var nodes = await r.json();
    showMsg("");
    renderNodes(nodes);
  } catch (err) {
    showMsg("Error: " + String(err.message || err), true);
  }
}

loadNodes();
setInterval(loadNodes, POLL_INTERVAL_MS);
