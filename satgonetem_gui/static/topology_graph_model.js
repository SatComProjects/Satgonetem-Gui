/** Pure filters, deterministic layout, partitions, and edge labels. */

export const UNASSIGNED_SHELL = "Unassigned";

function nameCompare(left, right) {
  return String(left?.name || "").localeCompare(String(right?.name || ""), undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

function shellOf(node) {
  return String(node?.shell || UNASSIGNED_SHELL);
}

export function shellOptions(nodes) {
  if (!Array.isArray(nodes)) return [];
  const shells = new Set();
  let hasUnassigned = false;
  for (const node of nodes) {
    if (node?.type !== "satellite") continue;
    if (node.shell) shells.add(String(node.shell));
    else hasUnassigned = true;
  }
  const ordered = [...shells].sort((left, right) => left.localeCompare(right));
  if (hasUnassigned) ordered.push(UNASSIGNED_SHELL);
  return ordered;
}

function matchesQuery(node, query) {
  if (!query) return true;
  return `${node?.name || ""} ${node?.city || ""} ${node?.type || ""} ${
    node?.type === "satellite" ? node?.shell || "" : ""
  }`
    .toLowerCase()
    .includes(query);
}

export function filterTopology(nodes, links, filters = {}) {
  const type = filters.type || "all";
  const shell = filters.shell || "all";
  const query = String(filters.query ?? "").trim().toLowerCase();
  const sourceNodes = Array.isArray(nodes) ? nodes : [];
  const visible = sourceNodes.filter((node) => {
    if (!node || typeof node !== "object") return false;
    if (type !== "all" && node.type !== type) return false;
    if (shell !== "all" && node.type === "satellite" && shellOf(node) !== shell) {
      return false;
    }
    return matchesQuery(node, query);
  });
  const names = new Set(visible.map((node) => node.name));
  const visibleLinks = (Array.isArray(links) ? links : []).filter(
    (link) => link && names.has(link.src) && names.has(link.dst),
  );
  return { nodes: visible, links: visibleLinks };
}

function ringPosition(center, radius, index, total, offset = 0) {
  const angle = -Math.PI / 2 + offset + (2 * Math.PI * index) / Math.max(1, total);
  return {
    x: Math.round((center.x + radius * Math.cos(angle)) * 100) / 100,
    y: Math.round((center.y + radius * Math.sin(angle)) * 100) / 100,
  };
}

/** Deterministic concentric-shell layout; returns name -> {x, y}. */
export function layoutTopology(nodes, { width = 1000, height = 700 } = {}) {
  const positions = {};
  if (!Array.isArray(nodes) || !nodes.length) return positions;
  const center = { x: width / 2, y: height / 2 };
  const extent = Math.min(width, height);

  const groups = new Map();
  const stations = [];
  for (const node of [...nodes].sort(nameCompare)) {
    if (!node) continue;
    if (node.type === "satellite") {
      const shell = shellOf(node);
      if (!groups.has(shell)) groups.set(shell, []);
      groups.get(shell).push(node);
    } else {
      stations.push(node);
    }
  }

  const shellNames = [...groups.keys()].sort((left, right) =>
    left.localeCompare(right),
  );
  const maxRadius = extent * 0.44;
  const minRadius = extent * 0.22;
  shellNames.forEach((shell, index) => {
    const radius =
      shellNames.length === 1
        ? maxRadius
        : maxRadius -
          (index * (maxRadius - minRadius)) / Math.max(1, shellNames.length - 1);
    const group = groups.get(shell);
    group.forEach((node, nodeIndex) => {
      positions[node.name] = ringPosition(
        center,
        radius,
        nodeIndex,
        group.length,
        index * 0.08,
      );
    });
  });

  const stationRadius = shellNames.length ? extent * 0.1 : extent * 0.3;
  stations.forEach((node, index) => {
    positions[node.name] = ringPosition(
      center,
      stationRadius,
      index,
      stations.length,
    );
  });
  return positions;
}

/** Connected components over the visible graph, sorted large-first. */
export function partitionTopology(nodes, links) {
  const records = Array.isArray(nodes) ? nodes : [];
  const adjacency = new Map(records.map((node) => [node.name, new Set()]));
  for (const link of Array.isArray(links) ? links : []) {
    if (!link || !adjacency.has(link.src) || !adjacency.has(link.dst)) continue;
    adjacency.get(link.src).add(link.dst);
    adjacency.get(link.dst).add(link.src);
  }
  const seen = new Set();
  const components = [];
  for (const node of [...records].sort(nameCompare)) {
    if (seen.has(node.name)) continue;
    const members = [];
    const queue = [node.name];
    seen.add(node.name);
    while (queue.length) {
      const current = queue.shift();
      members.push(current);
      for (const peer of adjacency.get(current) || []) {
        if (seen.has(peer)) continue;
        seen.add(peer);
        queue.push(peer);
      }
    }
    components.push(members.sort());
  }
  components.sort(
    (left, right) => right.length - left.length || left[0].localeCompare(right[0]),
  );
  const componentByNode = {};
  components.forEach((members, index) => {
    for (const name of members) componentByNode[name] = index;
  });
  return {
    count: components.length,
    components: components.map((members, index) => ({
      id: index,
      nodes: members,
    })),
    componentByNode,
  };
}

function numeric(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

export function edgeTooltip(link) {
  if (!link || typeof link !== "object") return "";
  return (
    `delay ${numeric(link.delay_ms).toFixed(1)} ms \u00b7 ` +
    `capacity ${Math.round(numeric(link.capacity_kbps))} kbps \u00b7 ` +
    `loss ${numeric(link.loss_percent).toFixed(1)}% \u00b7 ` +
    `jitter ${Math.round(numeric(link.jitter_ms))} ms`
  );
}
