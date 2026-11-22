/**
 * Pure helpers for the diagnostic forwarding-path view.
 *
 * The backend returns a path over the current routing graph, not a live
 * forwarding table. These helpers only format and identify that snapshot.
 */

const SPEED_OF_LIGHT_KM_PER_MS = 299.792458;

/**
 * Canonical undirected key for a topology link.
 *
 * @param {string} first
 * @param {string} second
 * @returns {string}
 */
export function linkKey(first, second) {
  return [String(first), String(second)].sort().join("|");
}

/**
 * @param {Array<{source: string, target: string}>} hops
 * @returns {Set<string>}
 */
export function pathLinkKeys(hops) {
  const keys = new Set();
  for (const hop of hops || []) {
    if (!hop || !hop.source || !hop.target) continue;
    keys.add(linkKey(hop.source, hop.target));
  }
  return keys;
}

/**
 * @param {{src?: string, dst?: string, hops?: Array<{source: string, target: string}>}} path
 * @returns {string}
 */
export function pathChain(path) {
  const hops = Array.isArray(path?.hops) ? path.hops : [];
  if (!hops.length) {
    if (path?.src && path?.dst) return `${path.src} \u2192 ${path.dst}`;
    return "";
  }
  return [hops[0].source, ...hops.map((hop) => hop.target)].join(" \u2192 ");
}

/**
 * @param {number|null|undefined} kilometers
 * @returns {string}
 */
export function formatDistance(kilometers) {
  if (kilometers === null || kilometers === undefined || kilometers === "") {
    return "-";
  }
  const value = Number(kilometers);
  if (!Number.isFinite(value)) return "-";
  return `${Number(value.toFixed(1))} km`;
}

/**
 * @param {number|null|undefined} milliseconds
 * @returns {string}
 */
export function formatDelay(milliseconds) {
  if (milliseconds === null || milliseconds === undefined || milliseconds === "") {
    return "-";
  }
  const value = Number(milliseconds);
  if (!Number.isFinite(value)) return "-";
  return `${Number(value.toFixed(2))} ms`;
}

/**
 * @param {string|null|undefined} type
 * @returns {string}
 */
export function pathLinkTypeLabel(type) {
  if (type === "GroundStationLink") return "GSL";
  if (type === "InterSatelliteLink") return "ISL";
  if (type === "UserTerminalLink") return "UT";
  return type || "-";
}

/**
 * @param {object|null|undefined} path
 * @returns {Array<{
 *   hop: number,
 *   source: string,
 *   target: string,
 *   link: string,
 *   type: string,
 *   direction: string,
 *   distance: string,
 *   delay: string,
 *   cumulativeDistance: string,
 *   cumulativeDelay: string,
 * }>}
 */
export function pathRows(path) {
  const hops = Array.isArray(path?.hops) ? path.hops : [];
  return hops.map((hop, index) => ({
    hop: index + 1,
    source: hop.source,
    target: hop.target,
    link: `${hop.source} \u2192 ${hop.target}`,
    type: pathLinkTypeLabel(hop.type),
    direction: hop.direction || "",
    distance: formatDistance(hop.distance_km),
    delay: formatDelay(hop.delay_ms),
    cumulativeDistance: formatDistance(hop.cumulative_distance_km),
    cumulativeDelay: formatDelay(hop.cumulative_delay_ms),
  }));
}

/**
 * @param {object|null|undefined} path
 * @returns {string}
 */
export function pathSummary(path) {
  if (!path) return "";
  if (!path.found) {
    return `No path found from ${path.src || "source"} to ${path.dst || "destination"}.`;
  }
  const routing = path.routing_method || "unknown";
  const live = path.routing_initiated ? "routing applied" : "routing not applied";
  return (
    `${path.node_count} nodes \u00b7 ${formatDistance(path.total_distance_km)}` +
    ` \u00b7 ${formatDelay(path.total_delay_ms)} \u00b7 ${routing} (${live})`
  );
}

export { SPEED_OF_LIGHT_KM_PER_MS };
