/** Pure labels for World View entities. */

import { escapeHtml } from "./escape.js";

function coordinateNumber(value) {
  if (value === null || value === undefined) return NaN;
  const text = String(value).trim();
  return text === "" ? NaN : Number(text);
}

export function hasPosition(position) {
  if (!position) return false;
  return (
    Number.isFinite(coordinateNumber(position.latitude)) &&
    Number.isFinite(coordinateNumber(position.longitude))
  );
}

export function retainedSelection(selected, names) {
  if (selected === null || selected === undefined) return null;
  const present = names instanceof Set ? names : new Set(names);
  return present.has(selected) ? selected : null;
}

export function formatCoordinate(value, digits = 2) {
  if (value === null || value === undefined) return "-";
  const text = String(value).trim();
  if (text === "") return "-";
  const number = Number(text);
  return Number.isFinite(number) ? number.toFixed(digits) : "-";
}

export function describeSatellite(name, position) {
  return (
    `<b>${escapeHtml(name)}</b><br>` +
    `Lat: ${formatCoordinate(position?.latitude)}<br>` +
    `Lon: ${formatCoordinate(position?.longitude)}<br>` +
    `Alt: ${formatCoordinate(position?.altitude, 0)} km`
  );
}

export function describeGroundStation(name, city, position, connected) {
  const cityLabel = city ? ` (${escapeHtml(city)})` : "";
  const status = connected ? "Connected" : "Disconnected";
  return (
    `<b>${escapeHtml(name)}${cityLabel}</b><br>` +
    `Lat: ${formatCoordinate(position?.latitude)}<br>` +
    `Lon: ${formatCoordinate(position?.longitude)}<br>` +
    `Status: ${status}`
  );
}

/** Classify a link for display and inspector counts. */
export function linkCategory(link) {
  const type = String(link?.type || "").toLowerCase();
  if (type.includes("groundstation") || type.includes("userterm")) return "gsl";
  if (String(link?.direction || "").toUpperCase() === "ADJACENT") {
    return "adjacent";
  }
  return "orbital";
}

/** Summarize the links incident to one node. */
export function summarizeLinks(links, name) {
  const key = String(name ?? "");
  const incident = (Array.isArray(links) ? links : [])
    .filter((link) => link && (link.src === key || link.dst === key))
    .map((link) => ({
      src: link.src,
      dst: link.dst,
      type: link.type,
      category: linkCategory(link),
      peer: link.src === key ? link.dst : link.src,
      is_active: link.is_active !== false,
    }));
  const byCategory = { gsl: 0, orbital: 0, adjacent: 0 };
  for (const link of incident) byCategory[link.category] += 1;
  return { total: incident.length, byCategory, incident };
}

function positionNumber(value) {
  if (value === null || value === undefined || value === "") return NaN;
  const number = Number(value);
  return Number.isFinite(number) ? number : NaN;
}

function haversineKm(left, right) {
  const radius = 6371.0;
  const toRadians = (degrees) => (degrees * Math.PI) / 180;
  const lat1 = toRadians(left.latitude);
  const lat2 = toRadians(right.latitude);
  const dLat = lat2 - lat1;
  const dLon = toRadians(right.longitude - left.longitude);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * radius * Math.asin(Math.min(1, Math.sqrt(a)));
}

function usablePosition(position) {
  if (!position) return null;
  const latitude = positionNumber(position.latitude);
  const longitude = positionNumber(position.longitude);
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return null;
  return { latitude, longitude };
}

/** Return the nearest other nodes by great-circle distance. */
export function nearestPeers(node, nodes, limit = 5) {
  const origin = usablePosition(node?.position);
  if (!origin || !Array.isArray(nodes)) return [];
  const peers = [];
  for (const candidate of nodes) {
    if (!candidate || candidate.name === node.name) continue;
    const position = usablePosition(candidate.position);
    if (!position) continue;
    peers.push({
      name: candidate.name,
      type: candidate.type || "node",
      distance_km: Math.round(haversineKm(origin, position) * 10) / 10,
    });
  }
  peers.sort((left, right) => left.distance_km - right.distance_km);
  return peers.slice(0, Math.max(0, Number(limit) || 0));
}

/** Read the `node` query parameter for a World deep link. */
export function deepLinkNode(search) {
  try {
    return new URLSearchParams(String(search || "")).get("node")?.trim() || null;
  } catch {
    return null;
  }
}
