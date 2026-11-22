/** Pure helpers for the server-side experiment runs page. */

export function experimentStatusLabel(status) {
  if (status === "running") return "Running";
  if (status === "done") return "Done";
  if (status === "error") return "Failed";
  return status || "Unknown";
}

export function formatExperimentDate(iso) {
  if (!iso) return "\u2014";
  return String(iso)
    .replace("T", " ")
    .replace(/\.\d+/, "")
    .replace(/Z$/, " UTC");
}

export function experimentModeLabel(mode) {
  if (mode === "dry_run") return "Validate only";
  if (mode === "offline") return "Offline";
  if (mode === "live") return "Live";
  return mode || "\u2014";
}

/**
 * @param {object|null|undefined} summary
 * @returns {string}
 */
export function experimentSummaryText(summary) {
  if (!summary || typeof summary !== "object") return "\u2014";
  const parts = [];
  const flows = summary.flows;
  if (flows && typeof flows === "object") {
    const count = Number(flows.count);
    if (Number.isFinite(count)) {
      const errors = Number(flows.errors);
      parts.push(
        `${count} flow${count === 1 ? "" : "s"}` +
          (Number.isFinite(errors) && errors > 0 ? ` (${errors} errors)` : ""),
      );
    }
  }
  const connectivity = summary.connectivity;
  if (connectivity && typeof connectivity === "object") {
    const reachable = Number(connectivity.reachable);
    const pairs = Number(connectivity.pairs);
    if (Number.isFinite(reachable) && Number.isFinite(pairs)) {
      parts.push(`${reachable}/${pairs} reachable`);
    }
  }
  if (!parts.length && Array.isArray(summary.errors) && summary.errors.length) {
    parts.push(`${summary.errors.length} error${summary.errors.length === 1 ? "" : "s"}`);
  }
  return parts.length ? parts.join(" \u00b7 ") : "\u2014";
}

export function artifactLabel(name) {
  const labels = {
    "manifest.yaml": "Manifest",
    "summary.json": "Summary",
    "report.md": "Report",
    "metrics.jsonl": "Metrics",
    "flows.json": "Flows",
    "connectivity.json": "Connectivity",
    "errors.json": "Errors",
    "provenance.json": "Provenance",
    "scenario.yaml": "Scenario",
  };
  return labels[name] || name;
}

export const DEFAULT_SCENARIO = `name: Demo Experiment
duration_s: 30
tick_s: 1
routing: static
metrics_interval_s: 5
connectivity: false
shells:
  - identifier: LEO
    planes: 3
    satellites_per_plane: 4
    inclination_deg: 53
    revs_per_day: 15.5
    pattern: star
ground_stations:
  - name: Berlin
    latitude: 52.52
    longitude: 13.405
    elevation_km: 0.034
`;
