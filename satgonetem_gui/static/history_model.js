/**
 * Pure helpers for the client-side experiment history.
 *
 * History is intentionally browser-local: the backend job registry is bounded
 * and evicts completed jobs, while this ledger keeps a compact copy of recent
 * successful runs for reopening, export, and comparison.
 */

export const HISTORY_KEY = "sgnt_traffic_history";
export const HISTORY_VERSION = 1;
export const MAX_HISTORY_RECORDS = 20;
export const MAX_HISTORY_BYTES = 2_000_000;
export const MAX_INTERVALS = 300;

function finiteNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function metric(label, value, unit) {
  const number = finiteNumber(value);
  return number === null ? null : { label, value: number, unit };
}

function compactMetrics(entries) {
  return entries.filter(Boolean);
}

/**
 * Keep a chart-sized copy of a result payload instead of storing every
 * interval produced by a long iperf3 run.
 *
 * @param {string} kind
 * @param {object|null|undefined} results
 * @param {number} [maxIntervals]
 * @returns {object|null}
 */
export function compactResults(kind, results, maxIntervals = MAX_INTERVALS) {
  if (!results || typeof results !== "object") return null;
  let copy;
  try {
    copy = JSON.parse(JSON.stringify(results));
  } catch {
    return null;
  }
  if (
    kind === "iperf3" &&
    Array.isArray(copy.intervals) &&
    copy.intervals.length > maxIntervals
  ) {
    const stride = Math.ceil(copy.intervals.length / maxIntervals);
    copy.intervals = copy.intervals
      .filter((_entry, index) => index % stride === 0)
      .slice(0, maxIntervals);
    copy.intervals_truncated = true;
  }
  return copy;
}

/**
 * Reduce a result payload to the metrics shown in the history table.
 *
 * @param {string} kind
 * @param {object|null|undefined} results
 * @returns {Array<{label: string, value: number, unit: string}>}
 */
export function summaryMetrics(kind, results) {
  if (!results || typeof results !== "object") return [];
  if (kind === "iperf3") {
    const metrics = [
      metric("Avg throughput", results.avg_throughput_mbps, "Mbps"),
      metric("Max throughput", results.max_throughput_mbps, "Mbps"),
      metric("Min throughput", results.min_throughput_mbps, "Mbps"),
    ];
    if ((results.protocol || "").toUpperCase() === "TCP") {
      metrics.push(
        metric("Retransmits", results.total_retransmits, ""),
        metric("Avg RTT", results.avg_rtt_ms, "ms"),
      );
    } else {
      metrics.push(
        metric("Loss", results.avg_loss_percent, "%"),
        metric("Jitter", results.avg_jitter_ms, "ms"),
      );
    }
    return compactMetrics(metrics);
  }
  return compactMetrics([
    metric("Loss", results.packet_loss_percent, "%"),
    metric("RTT avg", results.rtt_avg_ms, "ms"),
    metric("RTT min", results.rtt_min_ms, "ms"),
    metric("RTT max", results.rtt_max_ms, "ms"),
    metric(
      "Packets",
      results.packets_received != null ? results.packets_received : null,
      "",
    ),
  ]);
}

/**
 * Build one history record from a completed queue item.
 *
 * @param {object} options
 * @param {string} options.jobId
 * @param {string} options.kind
 * @param {string} options.label
 * @param {object} options.payload
 * @param {object|null} options.results
 * @param {number|null} [options.startedAt]
 * @param {number} [options.finishedAt]
 * @param {string|null} [options.projectName]
 * @param {string} [options.id]
 * @returns {object|null}
 */
export function buildHistoryRecord({
  jobId,
  kind,
  label,
  payload,
  results,
  startedAt = null,
  finishedAt = Date.now(),
  projectName = null,
  id = "",
}) {
  const compact = compactResults(kind, results);
  if (!compact) return null;
  const finished = finiteNumber(finishedAt) ?? Date.now();
  const started = finiteNumber(startedAt);
  const recordId =
    id ||
    `run-${finished}-${String(jobId || Math.random().toString(36).slice(2, 8))}`;
  return {
    id: recordId,
    job_id: jobId || null,
    kind,
    label: label || kind,
    payload: payload && typeof payload === "object" ? { ...payload } : {},
    project_name: projectName || null,
    recorded_at: new Date(finished).toISOString(),
    started_at: started === null ? null : new Date(started).toISOString(),
    finished_at: new Date(finished).toISOString(),
    duration_ms: started === null ? null : Math.max(0, finished - started),
    status: "done",
    results: compact,
    summary: summaryMetrics(kind, compact),
  };
}

function historyBytes(history) {
  try {
    return JSON.stringify(history).length;
  } catch {
    return MAX_HISTORY_BYTES + 1;
  }
}

/**
 * @param {object} history
 * @returns {{version: number, records: object[]}}
 */
export function trimHistory(history) {
  const records = Array.isArray(history?.records)
    ? history.records.slice(0, MAX_HISTORY_RECORDS)
    : [];
  while (records.length > 1 && historyBytes({ version: HISTORY_VERSION, records }) > MAX_HISTORY_BYTES) {
    records.pop();
  }
  return { version: HISTORY_VERSION, records };
}

/**
 * Accept either the stored envelope or a bare array and discard malformed
 * records defensively.
 *
 * @param {unknown} raw
 * @returns {{version: number, records: object[]}}
 */
export function normalizeHistory(raw) {
  const source = Array.isArray(raw)
    ? raw
    : raw && typeof raw === "object" && Array.isArray(raw.records)
      ? raw.records
      : [];
  const records = source
    .filter(
      (record) =>
        record &&
        typeof record === "object" &&
        typeof record.id === "string" &&
        typeof record.kind === "string" &&
        typeof record.recorded_at === "string" &&
        Number.isFinite(Date.parse(record.recorded_at)),
    )
    .map((record) => ({
      id: record.id,
      job_id: record.job_id || null,
      kind: record.kind,
      label: record.label || record.kind,
      payload: record.payload && typeof record.payload === "object" ? record.payload : {},
      project_name: record.project_name || null,
      recorded_at: record.recorded_at,
      started_at: record.started_at || null,
      finished_at: record.finished_at || record.recorded_at,
      duration_ms: finiteNumber(record.duration_ms),
      status: "done",
      results: record.results && typeof record.results === "object" ? record.results : null,
      summary: Array.isArray(record.summary)
        ? record.summary.filter(
            (entry) =>
              entry &&
              typeof entry.label === "string" &&
              finiteNumber(entry.value) !== null,
          )
        : summaryMetrics(record.kind, record.results),
    }))
    .sort((a, b) => Date.parse(b.recorded_at) - Date.parse(a.recorded_at));
  return trimHistory({ version: HISTORY_VERSION, records });
}

/**
 * Add a record, replacing the existing record for the same backend job.
 *
 * @param {object} history
 * @param {object} record
 * @returns {{version: number, records: object[]}}
 */
export function addHistoryRecord(history, record) {
  const normalized = normalizeHistory(history);
  const records = normalized.records.filter(
    (existing) =>
      existing.id !== record.id &&
      (!record.job_id || existing.job_id !== record.job_id),
  );
  records.unshift(record);
  return trimHistory({ version: HISTORY_VERSION, records });
}

/**
 * @param {object} history
 * @param {string} id
 * @returns {{version: number, records: object[]}}
 */
export function removeHistoryRecord(history, id) {
  const normalized = normalizeHistory(history);
  return trimHistory({
    version: HISTORY_VERSION,
    records: normalized.records.filter((record) => record.id !== id),
  });
}

function formatMetricValue(metricEntry) {
  const value = finiteNumber(metricEntry?.value);
  if (value === null) return "-";
  return `${Number(value.toFixed(2))}${metricEntry.unit ? ` ${metricEntry.unit}` : ""}`;
}

/**
 * @param {object} record
 * @returns {string}
 */
export function historySummaryText(record) {
  const summary = Array.isArray(record?.summary) ? record.summary : [];
  const preferred = [
    summary.find((entry) => /throughput/i.test(entry.label)),
    summary.find((entry) => /RTT avg/i.test(entry.label)),
    summary.find((entry) => /Loss/i.test(entry.label)),
  ].filter(Boolean);
  if (!preferred.length) return record?.kind || "run";
  return preferred.map(formatMetricValue).join(" \u00b7 ");
}

function csvEscape(value) {
  if (value === null || value === undefined) return "";
  const text = String(value);
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

const CSV_COLUMNS = [
  ["recorded_at", (record) => record.recorded_at],
  ["kind", (record) => record.kind],
  ["label", (record) => record.label],
  ["src", (record) => record.payload?.src],
  ["dst", (record) => record.payload?.dst],
  ["project", (record) => record.project_name],
  ["duration_ms", (record) => record.duration_ms],
  ["avg_throughput_mbps", (record) => record.results?.avg_throughput_mbps],
  ["max_throughput_mbps", (record) => record.results?.max_throughput_mbps],
  ["min_throughput_mbps", (record) => record.results?.min_throughput_mbps],
  ["total_retransmits", (record) => record.results?.total_retransmits],
  ["avg_rtt_ms", (record) => record.results?.avg_rtt_ms],
  ["packet_loss_percent", (record) => record.results?.packet_loss_percent],
  ["avg_jitter_ms", (record) => record.results?.avg_jitter_ms],
  ["packets_received", (record) => record.results?.packets_received],
  ["packets_transmitted", (record) => record.results?.packets_transmitted],
];

/**
 * @param {object} history
 * @returns {string}
 */
export function historyToCsv(history) {
  const normalized = normalizeHistory(history);
  const header = CSV_COLUMNS.map(([name]) => name).join(",");
  const rows = normalized.records.map((record) =>
    CSV_COLUMNS.map(([, read]) => csvEscape(read(record))).join(","),
  );
  return [header, ...rows].join("\n");
}

/**
 * @param {object} history
 * @param {number} [now]
 * @returns {string}
 */
export function historyToJson(history, now = Date.now()) {
  const normalized = normalizeHistory(history);
  return JSON.stringify(
    {
      version: HISTORY_VERSION,
      exported_at: new Date(now).toISOString(),
      records: normalized.records,
    },
    null,
    2,
  );
}

function intervalDelta(sum) {
  const seconds = finiteNumber(sum?.seconds);
  if (seconds !== null && seconds > 0) return seconds;
  const end = finiteNumber(sum?.end);
  const start = finiteNumber(sum?.start);
  if (end !== null && start !== null && end > start) return end - start;
  return 1;
}

function iperf3Series(record) {
  const intervals = Array.isArray(record?.results?.intervals)
    ? record.results.intervals
    : [];
  let elapsed = 0;
  const data = [];
  for (const entry of intervals) {
    const sum = entry?.sum || {};
    elapsed += intervalDelta(sum);
    data.push((finiteNumber(sum.bits_per_second) || 0) / 1e6);
  }
  return data;
}

function hping3Series(record) {
  return Array.isArray(record?.results?.rtt_ms)
    ? record.results.rtt_ms.map((value) => finiteNumber(value)).filter((value) => value !== null)
    : [];
}

function seriesFor(record) {
  if (record.kind === "iperf3") {
    return { label: "Throughput (Mbps)", data: iperf3Series(record) };
  }
  if (record.kind === "hping3") {
    return { label: "RTT (ms)", data: hping3Series(record) };
  }
  return null;
}

/**
 * Compare two runs. Summary rows are the primary artifact; a primary series is
 * included when both runs expose one (iperf3 throughput or hping3 RTT).
 *
 * @param {object} first
 * @param {object} second
 * @returns {{
 *   sameKind: boolean,
 *   rows: Array<{label: string, unit: string, first: number|null, second: number|null, delta: number|null}>,
 *   series: {label: string, first: number[], second: number[]}|null,
 * }}
 */
export function compareRuns(first, second) {
  const sameKind = first?.kind === second?.kind;
  const labels = [];
  const byLabel = new Map();
  for (const record of [first, second]) {
    for (const entry of record?.summary || []) {
      if (!byLabel.has(entry.label)) {
        byLabel.set(entry.label, { unit: entry.unit, first: null, second: null });
        labels.push(entry.label);
      }
    }
  }
  for (const [label, row] of byLabel) {
    row.first = first?.summary?.find((entry) => entry.label === label)?.value ?? null;
    row.second = second?.summary?.find((entry) => entry.label === label)?.value ?? null;
    row.delta =
      row.first !== null && row.second !== null
        ? finiteNumber((row.second - row.first).toFixed(2))
        : null;
  }
  const rows = labels.map((label) => ({ label, ...byLabel.get(label) }));

  let series = null;
  if (sameKind) {
    const firstSeries = seriesFor(first);
    const secondSeries = seriesFor(second);
    if (firstSeries && secondSeries) {
      const length = Math.max(firstSeries.data.length, secondSeries.data.length);
      const pad = (values) => Array.from({ length }, (_, index) => values[index] ?? null);
      series = {
        label: firstSeries.label,
        first: pad(firstSeries.data),
        second: pad(secondSeries.data),
      };
    }
  }
  return { sameKind, rows, series };
}
