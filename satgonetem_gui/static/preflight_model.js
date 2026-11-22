/**
 * Pure helpers for preflight diagnostics and honest project phase progress.
 */

/**
 * @param {Object|null|undefined} data
 * @returns {string}
 */
export function preflightSummary(data) {
  if (!data) return "Checking...";
  if (data.blocking) return "Blocked by a storage or configuration error.";
  const checks = Array.isArray(data.checks) ? data.checks : [];
  const warnings = checks.filter(
    (check) => check.status === "warning" || check.status === "unknown",
  ).length;
  if (warnings > 0) {
    return `Ready with ${warnings} warning${warnings === 1 ? "" : "s"}.`;
  }
  if (checks.length === 0) return "No checks were returned.";
  return "All checks passed.";
}

/**
 * @param {Object|null|undefined} estimate
 * @returns {string}
 */
export function formatEstimate(estimate) {
  if (!estimate) return "";
  const satellites = Number(estimate.satellites) || 0;
  const stations = Number(estimate.ground_stations) || 0;
  const containers = Number(estimate.containers) || 0;
  const memory = Number(estimate.estimated_memory_mb);
  const memoryText = Number.isFinite(memory)
    ? memory >= 1024
      ? `${Number((memory / 1024).toFixed(1))} GB`
      : `${Math.round(memory)} MB`
    : "unknown";
  return (
    `${satellites} satellite${satellites === 1 ? "" : "s"} \u00b7 ` +
    `${stations} ground station${stations === 1 ? "" : "s"} \u00b7 ` +
    `${containers} container${containers === 1 ? "" : "s"} \u00b7 ` +
    `~${memoryText} RAM (rough)`
  );
}

/**
 * @param {string|null|undefined} phase
 * @returns {string}
 */
export function phaseLabel(phase) {
  const labels = {
    idle: "Idle",
    validating: "Validating configuration",
    building: "Building topology",
    loading: "Loading project",
    finalizing: "Finalizing project",
    ready: "Ready",
    error: "Failed",
  };
  if (!phase) return "Working";
  return labels[phase] || phase.replaceAll("_", " ");
}

/**
 * @param {number|null|undefined} elapsedMs
 * @returns {string}
 */
export function formatElapsed(elapsedMs) {
  if (elapsedMs === null || elapsedMs === undefined || elapsedMs === "") {
    return "";
  }
  const value = Number(elapsedMs);
  if (!Number.isFinite(value) || value < 0) return "";
  if (value < 1000) return "<1 s";
  if (value < 60_000) return `${(value / 1000).toFixed(1)} s`;
  const minutes = Math.floor(value / 60_000);
  const seconds = Math.floor((value % 60_000) / 1000);
  return `${minutes}m ${String(seconds).padStart(2, "0")}s`;
}

/**
 * @param {number|null|undefined} progress
 * @returns {number|null}
 */
export function progressPercent(progress) {
  if (progress === null || progress === undefined || progress === "") return null;
  const value = Number(progress);
  if (!Number.isFinite(value)) return null;
  return Math.max(0, Math.min(100, Math.round(value)));
}

/**
 * @param {Array<{status: string}>|null|undefined} checks
 * @returns {boolean}
 */
export function hasBlockingCheck(checks) {
  return (Array.isArray(checks) ? checks : []).some(
    (check) => check && check.status === "error",
  );
}
