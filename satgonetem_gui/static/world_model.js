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
