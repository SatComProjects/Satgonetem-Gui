/** Pure helpers for the coverage analytics page. */

export function coverageClass(percent) {
  if (percent === null || percent === undefined || percent === "") {
    return "unknown";
  }
  const value = Number(percent);
  if (!Number.isFinite(value)) return "unknown";
  if (value <= 0) return "none";
  if (value < 50) return "low";
  if (value < 80) return "fair";
  return "good";
}

export function formatCoverage(percent) {
  if (percent === null || percent === undefined || percent === "") {
    return "\u2014";
  }
  const value = Number(percent);
  if (!Number.isFinite(value)) return "\u2014";
  return `${value.toFixed(1)}%`;
}

export function formatCount(value) {
  if (value === null || value === undefined || value === "") return "\u2014";
  const number = Number(value);
  if (!Number.isFinite(number)) return "\u2014";
  return new Intl.NumberFormat("en-US").format(Math.round(number));
}

export function formatDuration(milliseconds) {
  if (milliseconds === null || milliseconds === undefined || milliseconds === "") {
    return "\u2014";
  }
  const value = Number(milliseconds);
  if (!Number.isFinite(value)) return "\u2014";
  if (Math.abs(value) < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(1)} s`;
}

export function formatElevation(degrees) {
  if (degrees === null || degrees === undefined || degrees === "") {
    return "\u2014";
  }
  const value = Number(degrees);
  if (!Number.isFinite(value)) return "\u2014";
  return `${value.toFixed(1)}\u00b0`;
}

/** Covered stations first, then case-insensitive name order. */
export function sortGroundStations(stations) {
  if (!Array.isArray(stations)) return [];
  return [...stations].sort((left, right) => {
    const leftRank = left?.covered === true ? 0 : 1;
    const rightRank = right?.covered === true ? 0 : 1;
    if (leftRank !== rightRank) return leftRank - rightRank;
    return String(left?.name || "").localeCompare(String(right?.name || ""));
  });
}

export function coverageSummary(result) {
  if (!result || typeof result !== "object") return "\u2014";
  const parts = [];
  const satellites = Number(result.satellites);
  if (Number.isFinite(satellites)) {
    parts.push(
      `${satellites} satellite${satellites === 1 ? "" : "s"}`,
    );
  }
  const cells = Number(result.sampled_cells);
  if (Number.isFinite(cells)) {
    parts.push(`${formatCount(cells)} cells`);
  }
  const duration = Number(result.duration_ms);
  if (Number.isFinite(duration)) {
    parts.push(formatDuration(duration));
  }
  if (result.cached) parts.push("cached");
  return parts.length ? parts.join(" \u00b7 ") : "\u2014";
}

export function coverageNotes(result) {
  if (!result || typeof result !== "object") return "";
  const notes = [];
  if (result.shells_truncated) notes.push("Shell breakdown truncated.");
  if (result.ground_stations_truncated) {
    notes.push("Ground-station list truncated.");
  }
  return notes.join(" ");
}
