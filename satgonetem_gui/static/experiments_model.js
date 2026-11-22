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

function finiteNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

/**
 * Reduce raw metrics samples to one chart-friendly row per sample.
 * @param {object[]|null|undefined} samples
 * @returns {object[]}
 */
export function sampleSeries(samples) {
  if (!Array.isArray(samples)) return [];
  return samples.map((sample) => {
    const links = Array.isArray(sample?.links) ? sample.links : [];
    let tx = 0;
    let rx = 0;
    let active = 0;
    let lossTotal = 0;
    let lossCount = 0;
    for (const link of links) {
      if (!link || typeof link !== "object") continue;
      tx += finiteNumber(link.tx_bps);
      rx += finiteNumber(link.rx_bps);
      if (link.active === true) active += 1;
      if (typeof link.loss_percent === "number" && Number.isFinite(link.loss_percent)) {
        lossTotal += link.loss_percent;
        lossCount += 1;
      }
    }
    return {
      sim_time_s: finiteNumber(sample?.sim_time_s),
      tx_bps: tx,
      rx_bps: rx,
      active_links: active,
      avg_loss_percent: lossCount ? lossTotal / lossCount : 0,
    };
  });
}

/** Format a bit rate with the largest sensible unit. */
export function formatBps(value) {
  if (value === null || value === undefined || value === "") return "\u2014";
  const number = Number(value);
  if (!Number.isFinite(number)) return "\u2014";
  const units = [
    ["Gbps", 1e9],
    ["Mbps", 1e6],
    ["kbps", 1e3],
  ];
  for (const [unit, scale] of units) {
    if (Math.abs(number) >= scale) {
      return `${(number / scale).toFixed(1)} ${unit}`;
    }
  }
  return `${Math.round(number)} bps`;
}

function summaryObject(run) {
  return run && typeof run.summary === "object" && run.summary !== null
    ? run.summary
    : null;
}

function summaryMetric(run, key) {
  const summary = summaryObject(run);
  const metrics = summary?.metrics;
  if (!metrics || typeof metrics !== "object") return null;
  const value = Number(metrics[key]);
  return Number.isFinite(value) ? value : null;
}

function summaryFlowValue(run, key) {
  const flows = summaryObject(run)?.flows;
  if (!flows || typeof flows !== "object") return null;
  const value = Number(flows[key]);
  return Number.isFinite(value) ? value : null;
}

/**
 * Build the side-by-side comparison table rows.
 * @param {object[]} runs
 * @returns {{label: string, values: string[]}[]}
 */
export function compareTableRows(runs) {
  const records = Array.isArray(runs) ? runs : [];
  const simTime = records.map((run) => {
    const value = summaryMetric(run, "sim_time_s");
    return value === null ? "\u2014" : `${value} s`;
  });
  const sampleCounts = records.map((run) => {
    const value = summaryMetric(run, "samples");
    return value === null ? "\u2014" : String(value);
  });
  const bitRate = (key) =>
    records.map((run) => formatBps(summaryMetric(run, key)));
  const flowValue = (key) =>
    records.map((run) => {
      const value = summaryFlowValue(run, key);
      return value === null ? "\u2014" : String(value);
    });
  const simulatorErrors = records.map((run) => {
    const summary = summaryObject(run);
    const errors = summary?.metrics?.last_errors;
    return Array.isArray(errors) ? String(errors.length) : "\u2014";
  });
  const connectivity = records.map((run) => {
    const value = summaryObject(run)?.connectivity;
    const reachable = Number(value?.reachable);
    const pairs = Number(value?.pairs);
    return Number.isFinite(reachable) && Number.isFinite(pairs)
      ? `${reachable}/${pairs} reachable`
      : "\u2014";
  });

  return [
    {
      label: "Mode",
      values: records.map((run) => experimentModeLabel(run?.mode)),
    },
    {
      label: "Status",
      values: records.map((run) => experimentStatusLabel(run?.status)),
    },
    { label: "Simulation time", values: simTime },
    { label: "Samples", values: sampleCounts },
    { label: "Avg TX", values: bitRate("avg_tx_bps") },
    { label: "Max TX", values: bitRate("max_tx_bps") },
    { label: "Avg RX", values: bitRate("avg_rx_bps") },
    { label: "Max RX", values: bitRate("max_rx_bps") },
    { label: "Flows", values: flowValue("count") },
    { label: "Flow errors", values: flowValue("errors") },
    { label: "Simulator errors", values: simulatorErrors },
    { label: "Connectivity", values: connectivity },
    {
      label: "Started",
      values: records.map((run) => formatExperimentDate(run?.started_at)),
    },
  ];
}

const MAX_DIFF_LINES = 500;
const MAX_DIFF_CELLS = 250_000;

function scenarioLines(text) {
  if (typeof text !== "string" || !text) return [];
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  if (lines.length && lines[lines.length - 1] === "") lines.pop();
  return lines;
}

/**
 * Line diff of two scenario documents (baseline vs candidate).
 * @param {string} baselineText
 * @param {string} otherText
 * @returns {{kind: "same"|"add"|"remove"|"meta", text: string}[]}
 */
export function diffScenarioLines(baselineText, otherText) {
  const baseline = scenarioLines(baselineText);
  const other = scenarioLines(otherText);
  if (
    baseline.length > MAX_DIFF_LINES ||
    other.length > MAX_DIFF_LINES ||
    baseline.length * other.length > MAX_DIFF_CELLS
  ) {
    return [
      {
        kind: "meta",
        text: `Scenario too large to diff (${baseline.length} vs ${other.length} lines).`,
      },
    ];
  }

  const rows = baseline.length;
  const cols = other.length;
  const table = Array.from({ length: rows + 1 }, () => new Uint32Array(cols + 1));
  for (let row = rows - 1; row >= 0; row -= 1) {
    for (let col = cols - 1; col >= 0; col -= 1) {
      table[row][col] =
        baseline[row] === other[col]
          ? table[row + 1][col + 1] + 1
          : Math.max(table[row + 1][col], table[row][col + 1]);
    }
  }

  const diff = [];
  let row = 0;
  let col = 0;
  while (row < rows && col < cols) {
    if (baseline[row] === other[col]) {
      diff.push({ kind: "same", text: baseline[row] });
      row += 1;
      col += 1;
    } else if (table[row + 1][col] >= table[row][col + 1]) {
      diff.push({ kind: "remove", text: baseline[row] });
      row += 1;
    } else {
      diff.push({ kind: "add", text: other[col] });
      col += 1;
    }
  }
  while (row < rows) {
    diff.push({ kind: "remove", text: baseline[row] });
    row += 1;
  }
  while (col < cols) {
    diff.push({ kind: "add", text: other[col] });
    col += 1;
  }
  return diff;
}
