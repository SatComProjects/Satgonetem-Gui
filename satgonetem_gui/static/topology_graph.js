/** Deterministic network topology graph page. */
import { api } from "./api.js?v=4";
import { byId, setStatus } from "./dom.js";
import { escapeHtml } from "./escape.js";
import { linkKey, pathChain, pathLinkKeys } from "./path_model.js?v=1";
import {
  edgeTooltip,
  filterTopology,
  layoutTopology,
  partitionTopology,
  shellOptions,
} from "./topology_graph_model.js?v=1";

const SVG_NS = "http://www.w3.org/2000/svg";
const POLL_INTERVAL_MS = 5000;
const MAX_NODES = 1500;
const MAX_EDGES = 5000;

let allNodes = [];
let allLinks = [];
let pathKeys = new Set();
let selected = null;
let snapshots = [];
let diffState = { added: new Set(), removed: new Set(), changed: new Set(), extraLinks: [] };
let recording = false;
let pollTimer = null;
let searchTimer = null;
let fetching = false;

function setMessage(text, isError = false) {
  setStatus(byId("topo-msg"), text, isError);
}

function setPathMessage(text, isError = false) {
  setStatus(byId("topo-path-msg"), text, isError);
}

function filters() {
  return {
    shell: byId("topo-shell")?.value || "all",
    type: byId("topo-type")?.value || "all",
    query: byId("topo-search")?.value || "",
  };
}

function updateShellOptions() {
  const select = byId("topo-shell");
  if (!select) return;
  const current = select.value;
  const shells = shellOptions(allNodes);
  select.replaceChildren();
  const all = document.createElement("option");
  all.value = "all";
  all.textContent = "All shells";
  select.appendChild(all);
  for (const shell of shells) {
    const option = document.createElement("option");
    option.value = shell;
    option.textContent = shell;
    select.appendChild(option);
  }
  if (current === "all" || shells.includes(current)) select.value = current;
}

function nodeClass(node, component) {
  const classes = ["topo-node", node.type === "ground_station" ? "topo-ground" : "topo-satellite"];
  if (node.name === selected) classes.push("selected");
  if (component !== null) classes.push(`topo-component-${component % 8}`);
  return classes.join(" ");
}

function edgeElement(link, positions, highlightPartitions, componentByNode) {
  const source = positions[link.src];
  const target = positions[link.dst];
  if (!source || !target) return null;
  const line = document.createElementNS(SVG_NS, "line");
  line.setAttribute("x1", source.x);
  line.setAttribute("y1", source.y);
  line.setAttribute("x2", target.x);
  line.setAttribute("y2", target.y);
  const key = linkKey(link.src, link.dst);
  const classes = ["topo-edge"];
  if (link.is_active === false) classes.push("inactive");
  if (diffState.added.has(key)) classes.push("added");
  if (diffState.removed.has(key)) classes.push("removed");
  if (diffState.changed.has(key)) classes.push("changed");
  if (pathKeys.has(key)) classes.push("path");
  else if (pathKeys.size) classes.push("dim");
  if (highlightPartitions) {
    classes.push(`topo-component-${(componentByNode[link.src] ?? 0) % 8}`);
  }
  line.setAttribute("class", classes.join(" "));
  line.dataset.key = key;
  const title = document.createElementNS(SVG_NS, "title");
  title.textContent = `${link.src} \u2192 ${link.dst} \u00b7 ${edgeTooltip(link)}`;
  line.appendChild(title);
  return line;
}

function nodeElement(node, position, component) {
  const group = document.createElementNS(SVG_NS, "g");
  group.setAttribute("class", nodeClass(node, component));
  group.setAttribute("transform", `translate(${position.x} ${position.y})`);
  group.dataset.name = node.name;
  group.setAttribute("tabindex", "0");
  group.setAttribute("role", "button");
  group.setAttribute("aria-label", `${node.name} ${node.type}`);
  const title = document.createElementNS(SVG_NS, "title");
  title.textContent = `${node.name} \u00b7 ${node.type}${node.city ? ` \u00b7 ${node.city}` : ""}`;
  group.appendChild(title);
  if (node.type === "ground_station") {
    const rect = document.createElementNS(SVG_NS, "rect");
    rect.setAttribute("x", "-5");
    rect.setAttribute("y", "-5");
    rect.setAttribute("width", "10");
    rect.setAttribute("height", "10");
    rect.setAttribute("rx", "2");
    group.appendChild(rect);
    const label = document.createElementNS(SVG_NS, "text");
    label.setAttribute("x", "8");
    label.setAttribute("y", "4");
    label.textContent = node.name;
    group.appendChild(label);
  } else {
    const circle = document.createElementNS(SVG_NS, "circle");
    circle.setAttribute("r", "5");
    group.appendChild(circle);
  }
  group.addEventListener("click", (event) => {
    event.stopPropagation();
    selectNode(node.name);
  });
  group.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    selectNode(node.name);
  });
  return group;
}

function renderGraph() {
  const container = byId("topology-graph");
  if (!container) return;
  const filtered = filterTopology(allNodes, allLinks, filters());
  let nodes = filtered.nodes;
  let links = filtered.links;
  let overflow = "";
  if (nodes.length > MAX_NODES) {
    const keep = new Set([...nodes].sort((a, b) => a.name.localeCompare(b.name)).slice(0, MAX_NODES).map((n) => n.name));
    nodes = nodes.filter((node) => keep.has(node.name));
    links = links.filter((link) => keep.has(link.src) && keep.has(link.dst));
    overflow = `Showing ${MAX_NODES} of ${filtered.nodes.length} nodes; narrow the filters to see the rest.`;
  }
  if (links.length > MAX_EDGES) {
    links = links.slice(0, MAX_EDGES);
    overflow = `${overflow} Showing ${MAX_EDGES} links.`.trim();
  }
  const overflowElement = byId("topo-overflow");
  if (overflowElement) {
    overflowElement.textContent = overflow;
    overflowElement.hidden = !overflow;
  }

  const partitions = partitionTopology(nodes, links);
  const count = byId("topo-count");
  if (count) {
    count.textContent = `${nodes.length} node${nodes.length === 1 ? "" : "s"} \u00b7 ${links.length} link${links.length === 1 ? "" : "s"}`;
  }
  const partitionCount = byId("topo-partition-count");
  if (partitionCount) {
    partitionCount.textContent = `${partitions.count} partition${partitions.count === 1 ? "" : "s"}`;
  }
  const empty = byId("topo-empty");
  if (empty) empty.hidden = nodes.length > 0;

  const positions = layoutTopology(nodes, { width: 1000, height: 700 });
  const highlightPartitions = Boolean(byId("topo-partitions")?.checked);
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", "0 0 1000 700");
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", `Network graph with ${nodes.length} nodes and ${links.length} links`);
  for (const link of links) {
    const line = edgeElement(
      link,
      positions,
      highlightPartitions,
      partitions.componentByNode,
    );
    if (line) svg.appendChild(line);
  }
  for (const link of diffState.extraLinks) {
    if (!positions[link.src] || !positions[link.dst]) continue;
    const ghost = edgeElement(
      link,
      positions,
      false,
      partitions.componentByNode,
    );
    if (ghost) {
      ghost.classList.add("removed");
      svg.appendChild(ghost);
    }
  }
  for (const node of nodes) {
    const position = positions[node.name];
    if (!position) continue;
    svg.appendChild(
      nodeElement(
        node,
        position,
        highlightPartitions ? partitions.componentByNode[node.name] ?? 0 : null,
      ),
    );
  }
  svg.addEventListener("click", (event) => {
    if (event.target === svg) closeInspector();
  });
  container.replaceChildren(svg);
  populatePathSelects(nodes);
  if (selected && !nodes.some((node) => node.name === selected)) {
    closeInspector();
  }
}

function fillPathSelect(select, nodes) {
  const previous = select.value;
  select.replaceChildren();
  for (const node of [...nodes].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }))) {
    const option = document.createElement("option");
    option.value = node.name;
    option.textContent = node.name;
    select.appendChild(option);
  }
  if (nodes.some((node) => node.name === previous)) select.value = previous;
  select.disabled = nodes.length < 2;
}

function populatePathSelects(nodes) {
  const source = byId("topo-path-src");
  const destination = byId("topo-path-dst");
  const trace = byId("topo-path-trace");
  const clear = byId("topo-path-clear");
  if (!source || !destination) return;
  fillPathSelect(source, nodes);
  fillPathSelect(destination, nodes);
  if (!source.value && nodes.length) source.value = nodes[0].name;
  if (!destination.value && nodes.length > 1) destination.value = nodes[1].name;
  const enabled = nodes.length >= 2;
  if (trace) trace.disabled = !enabled;
  if (clear) clear.disabled = !enabled;
  if (!enabled) setPathMessage("Load at least two visible nodes to trace a path.");
}

function renderInspector(node) {
  const panel = byId("topo-inspector");
  if (!panel) return;
  panel.hidden = false;
  const title = byId("topo-inspector-title");
  if (title) title.textContent = node.name || "Node";
  const kind = byId("topo-inspector-kind");
  if (kind) {
    kind.textContent =
      node.type === "ground_station"
        ? `Ground station${node.city ? ` \u00b7 ${node.city}` : ""}`
        : "Satellite";
  }
  const position = byId("topo-inspector-position");
  if (position) {
    const values = [
      ["Latitude", node.position?.latitude],
      ["Longitude", node.position?.longitude],
      ["Altitude", node.position?.altitude],
    ];
    position.replaceChildren();
    for (const [label, value] of values) {
      const cell = document.createElement("div");
      const term = document.createElement("dt");
      term.textContent = label;
      const detail = document.createElement("dd");
      detail.textContent = value === null || value === undefined ? "\u2014" : String(value);
      cell.append(term, detail);
      position.appendChild(cell);
    }
  }
  const interfaces = byId("topo-inspector-interfaces");
  if (interfaces) {
    const rows = Array.isArray(node.interfaces) ? node.interfaces : [];
    interfaces.innerHTML = `<h4>Interfaces</h4>${
      rows.length
        ? `<table class="topo-table"><thead><tr><th>Name</th><th>IPv4</th><th>Peer</th></tr></thead><tbody>${rows
            .map(
              (iface) =>
                `<tr><td>${escapeHtml(iface.name || "-")}</td><td>${escapeHtml(iface.ipv4 || "-")}</td><td>${escapeHtml(iface.peer_name || "-")}</td></tr>`,
            )
            .join("")}</tbody></table>`
        : '<p class="muted">No interfaces reported.</p>'
    }`;
  }
  const routing = byId("topo-inspector-routing");
  if (routing) {
    const table = Array.isArray(node.routing_table) ? node.routing_table : [];
    routing.innerHTML = `<h4>Routing table</h4>${
      table.length
        ? `<pre class="topo-routing">${escapeHtml(table.join("\n"))}</pre>`
        : '<p class="muted">No routing table available (containers may not be running).</p>'
    }`;
  }
}

async function selectNode(name) {
  selected = name;
  renderGraph();
  try {
    const data = await api.get(`/api/nodes/${encodeURIComponent(name)}`);
    if (selected !== name) return;
    renderInspector(data.node);
  } catch (error) {
    setMessage(error.message || "Could not load node details.", true);
  }
}

function closeInspector() {
  const panel = byId("topo-inspector");
  if (panel) panel.hidden = true;
  if (selected) {
    selected = null;
    renderGraph();
  }
}

async function tracePath() {
  const source = byId("topo-path-src")?.value;
  const destination = byId("topo-path-dst")?.value;
  if (!source || !destination) {
    setPathMessage("Choose a source and destination.", true);
    return;
  }
  if (source === destination) {
    setPathMessage("Choose different source and destination nodes.", true);
    return;
  }
  setPathMessage("Tracing path...");
  try {
    const data = await api.get(
      `/api/routing/path?src=${encodeURIComponent(source)}&dst=${encodeURIComponent(destination)}`,
    );
    pathKeys = pathLinkKeys(data.hops);
    const summary = byId("topo-path-summary");
    if (summary) summary.textContent = pathChain(data);
    setPathMessage(
      data.found
        ? `${data.node_count} hops \u00b7 ${Number(data.total_delay_ms || 0).toFixed(2)} ms`
        : "No path found in the current routing graph.",
      !data.found,
    );
    renderGraph();
  } catch (error) {
    pathKeys = new Set();
    const summary = byId("topo-path-summary");
    if (summary) summary.textContent = "";
    setPathMessage(error.message || "Could not trace the path.", true);
    renderGraph();
  }
}

function clearPath() {
  pathKeys = new Set();
  const summary = byId("topo-path-summary");
  if (summary) summary.textContent = "";
  setPathMessage("");
  renderGraph();
}

function historyMessage(text, isError = false) {
  setStatus(byId("topo-history-msg"), text, isError);
}

function compareMessage(text, isError = false) {
  setStatus(byId("topo-compare-msg"), text, isError);
}

function fillSnapshotSelect(select, records) {
  const previous = select.value;
  select.replaceChildren();
  for (const snapshot of records) {
    const option = document.createElement("option");
    option.value = String(snapshot.step);
    option.textContent = `step ${snapshot.step}${snapshot.time ? ` \u00b7 ${snapshot.time}` : ""}`;
    select.appendChild(option);
  }
  if (records.some((snapshot) => String(snapshot.step) === previous)) {
    select.value = previous;
  }
  select.disabled = records.length < 2;
}

async function loadSnapshots() {
  try {
    const data = await api.get("/api/topology/snapshots");
    snapshots = Array.isArray(data.snapshots) ? data.snapshots : [];
    const from = byId("topo-compare-from");
    const to = byId("topo-compare-to");
    if (from) fillSnapshotSelect(from, snapshots);
    if (to) fillSnapshotSelect(to, snapshots);
    if (snapshots.length >= 2) {
      if (!from.value) from.value = String(snapshots[snapshots.length - 2].step);
      if (!to.value) to.value = String(snapshots[snapshots.length - 1].step);
    }
    const count = byId("topo-snapshot-count");
    if (count) count.textContent = `${snapshots.length} recorded`;
    const compare = byId("topo-compare");
    if (compare) compare.disabled = snapshots.length < 2;
  } catch (error) {
    historyMessage(error.message || "Could not load snapshots.", true);
  }
}

async function recordSnapshot(manual = false) {
  if (recording) return;
  recording = true;
  try {
    const data = await api.post("/api/topology/snapshots", undefined);
    if (manual) {
      historyMessage(
        data.recorded
          ? `Recorded step ${data.step}.`
          : `Step ${data.step} is already recorded.`,
      );
    }
    await loadSnapshots();
  } catch (error) {
    if (manual) {
      historyMessage(
        error.status === 404
          ? "Load a project before recording snapshots."
          : error.message || "Could not record a snapshot.",
        true,
      );
    }
  } finally {
    recording = false;
  }
}

function diffRow(kind, element, details) {
  return `<tr data-diff="${kind}"><td>${kind[0].toUpperCase() + kind.slice(1)}</td><td>${escapeHtml(element)}</td><td>${escapeHtml(details)}</td></tr>`;
}

function renderComparison(data) {
  const added = Array.isArray(data.added_links) ? data.added_links : [];
  const removed = Array.isArray(data.removed_links) ? data.removed_links : [];
  const changed = Array.isArray(data.changed_links) ? data.changed_links : [];
  const addedNodes = Array.isArray(data.added_nodes) ? data.added_nodes : [];
  const removedNodes = Array.isArray(data.removed_nodes) ? data.removed_nodes : [];
  diffState = {
    added: new Set(added.map((link) => linkKey(link.src, link.dst))),
    removed: new Set(removed.map((link) => linkKey(link.src, link.dst))),
    changed: new Set(changed.map((link) => linkKey(link.src, link.dst))),
    extraLinks: removed,
  };
  const rows = [
    ...added.map((link) =>
      diffRow("added", `${link.src} \u2192 ${link.dst}`, link.type || "link"),
    ),
    ...removed.map((link) =>
      diffRow("removed", `${link.src} \u2192 ${link.dst}`, link.type || "link"),
    ),
    ...changed.map((link) =>
      diffRow(
        "changed",
        `${link.src} \u2192 ${link.dst}`,
        (link.changes || []).join(", "),
      ),
    ),
    ...addedNodes.map((name) => diffRow("added", name, "node")),
    ...removedNodes.map((name) => diffRow("removed", name, "node")),
  ];
  const container = byId("topo-compare-table");
  if (container) {
    container.innerHTML = rows.length
      ? `<table class="topo-table topo-diff-table"><thead><tr><th>Change</th><th>Element</th><th>Details</th></tr></thead><tbody>${rows.join("")}</tbody></table>`
      : '<p class="muted">No differences between these steps.</p>';
  }
  compareMessage(
    `${added.length} added / ${removed.length} removed / ${changed.length} changed links \u00b7 nodes +${addedNodes.length}/-${removedNodes.length}`,
  );
  renderGraph();
}

async function compareSteps() {
  const from = byId("topo-compare-from")?.value;
  const to = byId("topo-compare-to")?.value;
  if (from === undefined || to === undefined) {
    compareMessage("Record at least two steps before comparing.", true);
    return;
  }
  compareMessage("Comparing...");
  try {
    const data = await api.get(
      `/api/topology/compare?from_step=${encodeURIComponent(from)}&to_step=${encodeURIComponent(to)}`,
    );
    renderComparison(data);
  } catch (error) {
    diffState = { added: new Set(), removed: new Set(), changed: new Set(), extraLinks: [] };
    compareMessage(error.message || "Could not compare steps.", true);
    renderGraph();
  }
}

async function loadData() {
  if (fetching) return;
  fetching = true;
  try {
    const [nodes, links] = await Promise.all([
      api.getAll("/api/nodes"),
      api.getAll("/api/links"),
    ]);
    allNodes = Array.isArray(nodes) ? nodes : [];
    allLinks = Array.isArray(links) ? links : [];
    updateShellOptions();
    renderGraph();
    setMessage("");
    await recordSnapshot(false);
  } catch (error) {
    allNodes = [];
    allLinks = [];
    renderGraph();
    setMessage(
      error.status === 404
        ? "Load a project to render the network graph."
        : error.message || "Could not load the topology.",
      true,
    );
  } finally {
    fetching = false;
  }
}

byId("topo-shell")?.addEventListener("change", renderGraph);
byId("topo-type")?.addEventListener("change", renderGraph);
byId("topo-partitions")?.addEventListener("change", renderGraph);
byId("topo-search")?.addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(renderGraph, 120);
});
byId("topo-record")?.addEventListener("click", () => recordSnapshot(true));
byId("topo-compare")?.addEventListener("click", compareSteps);
byId("topo-path-trace")?.addEventListener("click", tracePath);
byId("topo-path-clear")?.addEventListener("click", clearPath);
byId("topo-inspector-close")?.addEventListener("click", closeInspector);
window.addEventListener("pagehide", () => clearInterval(pollTimer), { once: true });

loadData();
pollTimer = setInterval(loadData, POLL_INTERVAL_MS);
