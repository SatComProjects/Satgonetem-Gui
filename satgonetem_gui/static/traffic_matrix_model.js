/** Pure formatting and heat levels for the throughput matrix. */

export function formatThroughput(value) {
  if (value === null || value === undefined || value === "") return "\u2014";
  const number = Number(value);
  if (!Number.isFinite(number)) return "\u2014";
  return `${number.toFixed(1)} Mbps`;
}

export function statusLabel(status) {
  if (status === "running") return "Running";
  if (status === "done") return "Done";
  if (status === "error") return "Failed";
  return status || "\u2014";
}

export function matrixSummary(job) {
  if (!job || typeof job !== "object") return "\u2014";
  return `${statusLabel(job.status)} \u00b7 ${Number(job.pairs_completed) || 0}/${Number(job.pairs_total) || 0} pairs`;
}

export function matrixMax(matrix) {
  let maximum = 0;
  for (const row of Array.isArray(matrix) ? matrix : []) {
    for (const cell of Array.isArray(row) ? row : []) {
      const value = Number(cell);
      if (Number.isFinite(value) && value > maximum) maximum = value;
    }
  }
  return maximum;
}

export function heatLevel(value, maximum) {
  const number = Number(value);
  const max = Number(maximum);
  if (!Number.isFinite(number) || !Number.isFinite(max) || max <= 0) return 0;
  if (number <= 0) return 0;
  const ratio = number / max;
  if (ratio >= 0.75) return 4;
  if (ratio >= 0.5) return 3;
  if (ratio >= 0.2) return 2;
  return 1;
}
