/**
 * Pure helpers for the per-node link inspector.
 *
 * Link metrics are snapshots from `/api/links`; formatting and filtering stay
 * here so both the Node Explorer and World View use the same rules.
 */

/**
 * @param {object} link
 * @param {string} name
 * @returns {string}
 */
export function linkPeer(link, name) {
  if (!link) return "";
  return link.src === name ? link.dst : link.src;
}

/**
 * @param {Array<object>|null|undefined} links
 * @param {string} name
 * @returns {Array<object>}
 */
export function linksForNode(links, name) {
  return (Array.isArray(links) ? links : [])
    .filter((link) => link && (link.src === name || link.dst === name))
    .sort((a, b) =>
      linkPeer(a, name).localeCompare(linkPeer(b, name), undefined, {
        numeric: true,
      }),
    );
}

/**
 * @param {number|null|undefined} kbps
 * @returns {string}
 */
export function formatCapacityKbps(kbps) {
  if (kbps === null || kbps === undefined || kbps === "") return "Unknown";
  const value = Number(kbps);
  if (!Number.isFinite(value) || value <= 0) return "Unknown";
  if (value >= 1_000_000) return `${Number((value / 1_000_000).toFixed(2))} Gbps`;
  if (value >= 1_000) return `${Number((value / 1_000).toFixed(2))} Mbps`;
  return `${Math.round(value)} kbps`;
}

/**
 * @param {number|null|undefined} milliseconds
 * @returns {string}
 */
export function formatLinkDelay(milliseconds) {
  if (milliseconds === null || milliseconds === undefined || milliseconds === "") {
    return "Unknown";
  }
  const value = Number(milliseconds);
  if (!Number.isFinite(value)) return "Unknown";
  return `${Number(value.toFixed(2))} ms`;
}

/**
 * @param {string|null|undefined} type
 * @returns {string}
 */
export function linkTypeLabel(type) {
  if (type === "GroundStationLink") return "GSL";
  if (type === "InterSatelliteLink") return "ISL";
  if (type === "UserTerminalLink") return "UT";
  return type || "-";
}

/**
 * @param {object} link
 * @returns {string}
 */
export function linkDirectionLabel(link) {
  if (!link) return "-";
  if (link.type === "GroundStationLink") return "Ground";
  const direction = String(link.direction || "").toUpperCase();
  if (direction === "ORBITAL") return "Orbital";
  if (direction === "ADJACENT") return "Adjacent";
  return link.direction || "-";
}

/**
 * @param {boolean|null|undefined} isActive
 * @returns {string}
 */
export function linkStateLabel(isActive) {
  return isActive === false ? "Inactive" : "Active";
}

/**
 * Width for a Cesium polyline: capacity is compressed logarithmically so a
 * 1 Gbps link is visibly thicker than a 1 Mbps link without dwarfing it.
 *
 * @param {number|null|undefined} capacityKbps
 * @param {boolean} [onPath]
 * @returns {number}
 */
export function linkWidth(capacityKbps, onPath = false) {
  if (onPath) return 4.0;
  const value = Number(capacityKbps);
  if (!Number.isFinite(value) || value <= 0) return 1.0;
  const scaled = 1 + Math.log10(value / 1_000);
  return Math.max(1.0, Math.min(3.5, Number(scaled.toFixed(2))));
}

/**
 * Interpolate a usage ratio from green (no usage) through amber (half) to red
 * (at or above capacity). Unknown capacity/usage is a neutral slate.
 *
 * @param {number|null|undefined} ratio
 * @returns {string} CSS rgb() color.
 */
export function usageColor(ratio) {
  if (ratio === null || ratio === undefined || ratio === "") {
    return "rgb(100, 116, 139)";
  }
  const value = Number(ratio);
  if (!Number.isFinite(value)) return "rgb(100, 116, 139)";
  const clamped = Math.max(0, Math.min(1, value));
  const start = clamped <= 0.5 ? [34, 197, 94] : [234, 179, 8];
  const end = clamped <= 0.5 ? [234, 179, 8] : [239, 68, 68];
  const t = clamped <= 0.5 ? clamped / 0.5 : (clamped - 0.5) / 0.5;
  const channels = start.map((from, index) =>
    Math.round(from + (end[index] - from) * t),
  );
  return `rgb(${channels[0]}, ${channels[1]}, ${channels[2]})`;
}
