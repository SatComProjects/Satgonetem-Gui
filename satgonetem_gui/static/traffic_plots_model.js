/**
 * Pure extraction helpers for traffic result payloads.
 *
 * The queue and history views hand raw iperf3/ping/hping3 result JSON to these
 * functions to obtain chart series and results-modal metric rows. There is no
 * DOM, no Chart.js, and no page state here so the transforms stay deterministic
 * and Vitest-covered.
 *
 * Non-finite numbers (NaN, Infinity, unparsable strings) are sanitized to
 * `null` for optional chart points and to `0` for required aggregates, so a
 * malformed result never injects NaN into a chart scale.
 */
import { escapeHtml } from "./escape.js";

function finiteNumber(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function finiteOr(value, fallback) {
  const number = finiteNumber(value);
  return number === null ? fallback : number;
}

function finiteSeries(values) {
  if (!Array.isArray(values)) return [];
  return values.map((value) => finiteNumber(value));
}

function intervalDelta(sum) {
  let delta;
  if (sum.seconds !== null && sum.seconds !== undefined) {
    delta = Number(sum.seconds);
  } else if (
    sum.end !== null &&
    sum.end !== undefined &&
    sum.start !== null &&
    sum.start !== undefined
  ) {
    delta = Number(sum.end) - Number(sum.start);
  } else {
    delta = 1;
  }
  return Number.isFinite(delta) && delta > 0 ? delta : 1;
}

function lossFromPackets(source) {
  const lost = finiteNumber(source.lost_packets);
  const packets = finiteNumber(source.packets);
  if (lost === null || packets === null || packets <= 0) return null;
  return (lost / packets) * 100;
}

/**
 * Build every chart series the iperf3 results panel needs.
 *
 * @param {object|null|undefined} result - iperf3 result payload.
 * @returns {{
 *   isTcp: boolean,
 *   isUdp: boolean,
 *   streamCount: number,
 *   times: number[],
 *   throughput: number[],
 *   cumulativeBits: number[],
 *   cwnd: Array<number|null>,
 *   rtt: Array<number|null>,
 *   aux: number[],
 *   jitter: number[],
 *   perThroughput: Array<Array<number|null>>,
 *   perCwnd: Array<Array<number|null>>,
 *   perRtt: Array<Array<number|null>>,
 *   perJitter: Array<Array<number|null>>,
 *   perAux: Array<Array<number|null>>,
 * }}
 */
export function buildIperf3Series(result) {
  const data = result && typeof result === "object" ? result : {};
  const isTcp = String(data.protocol || "").toUpperCase() === "TCP";
  const intervals = Array.isArray(data.intervals) ? data.intervals : [];
  const streamCount = intervals.reduce(
    (max, entry) =>
      Math.max(max, Array.isArray(entry?.streams) ? entry.streams.length : 0),
    0,
  );
  const series = {
    isTcp,
    isUdp: !isTcp,
    streamCount,
    times: [],
    throughput: [],
    cumulativeBits: [],
    cwnd: [],
    rtt: [],
    aux: [],
    jitter: [],
    perThroughput: Array.from({ length: streamCount }, () => []),
    perCwnd: Array.from({ length: streamCount }, () => []),
    perRtt: Array.from({ length: streamCount }, () => []),
    perJitter: Array.from({ length: streamCount }, () => []),
    perAux: Array.from({ length: streamCount }, () => []),
  };

  let cumulative = 0;
  let elapsed = 0;
  for (const entry of intervals) {
    const sum = entry?.sum || {};
    const bitsPerSecond = finiteOr(sum.bits_per_second, 0);
    const bytes = finiteOr(sum.bytes, 0);
    elapsed += intervalDelta(sum);
    cumulative += bytes * 8;
    series.times.push(elapsed);
    series.throughput.push(bitsPerSecond / 1e6);
    series.cumulativeBits.push(cumulative / 1e6);

    if (isTcp) {
      const stream = (entry?.streams && entry.streams[0]) || {};
      const congestionWindow = finiteNumber(stream.snd_cwnd);
      series.cwnd.push(
        congestionWindow === null ? null : congestionWindow / 1024.0,
      );
      const streamRtt = finiteNumber(stream.rtt);
      series.rtt.push(streamRtt === null ? null : streamRtt / 1000.0);
      series.aux.push(finiteOr(stream.retransmits, 0));
      for (let index = 0; index < streamCount; index += 1) {
        const itemStream = (entry?.streams && entry.streams[index]) || {};
        const streamThroughput = finiteNumber(itemStream.bits_per_second);
        series.perThroughput[index].push(
          streamThroughput === null ? null : streamThroughput / 1e6,
        );
        const itemCwnd = finiteNumber(itemStream.snd_cwnd);
        series.perCwnd[index].push(
          itemCwnd === null ? null : itemCwnd / 1024.0,
        );
        const itemRtt = finiteNumber(itemStream.rtt);
        series.perRtt[index].push(
          itemRtt === null ? null : itemRtt / 1000.0,
        );
        series.perAux[index].push(finiteNumber(itemStream.retransmits));
      }
    } else {
      let loss = finiteNumber(sum.lost_percent);
      if (loss === null) loss = lossFromPackets(sum);
      if (loss === null) {
        const first = (entry?.streams && entry.streams[0]) || {};
        loss = finiteNumber(first.lost_percent);
        if (loss === null) loss = lossFromPackets(first);
      }
      series.aux.push(loss === null ? 0 : loss);
      for (let index = 0; index < streamCount; index += 1) {
        const itemStream = (entry?.streams && entry.streams[index]) || {};
        const streamThroughput = finiteNumber(itemStream.bits_per_second);
        series.perThroughput[index].push(
          streamThroughput === null ? null : streamThroughput / 1e6,
        );
        series.perJitter[index].push(finiteNumber(itemStream.jitter_ms));
        let lostPercent = finiteNumber(itemStream.lost_percent);
        if (lostPercent === null) lostPercent = lossFromPackets(itemStream);
        series.perAux[index].push(lostPercent);
      }

      let jitterMs = null;
      if (sum.jitter_ms !== null && sum.jitter_ms !== undefined) {
        jitterMs = finiteNumber(sum.jitter_ms);
      } else {
        const first = (entry?.streams && entry.streams[0]) || {};
        jitterMs = finiteNumber(first.jitter_ms);
      }
      let value = jitterMs === null ? 0 : jitterMs;
      if (!(value > 0)) value = 0.001;
      series.jitter.push(value);
    }
  }
  return series;
}

/**
 * Build the labels and series for the two hping3 charts.
 *
 * @param {object|null|undefined} result - hping3 result payload.
 * @returns {{labels: string[], rtt: Array<number|null>, cumulativeMbit: Array<number|null>}}
 */
export function buildHping3Series(result) {
  const data = result && typeof result === "object" ? result : {};
  const seq = Array.isArray(data.seq) ? data.seq : [];
  return {
    labels: seq.map((value) => String(value)),
    rtt: finiteSeries(data.rtt_ms),
    cumulativeMbit: finiteSeries(data.cumulative_mbit),
  };
}

/**
 * Format a scalar the way the results modal always has.
 *
 * @param {unknown} value
 * @returns {string}
 */
export function fmt(value) {
  if (value === null || value === undefined || value !== value) return "-";
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(2) : String(value);
}

/**
 * Format a byte count with a binary-ish decimal unit suffix.
 *
 * @param {unknown} bytes
 * @returns {string}
 */
export function fmtBytes(bytes) {
  if (bytes === null || bytes === undefined) return "-";
  const number = Number(bytes);
  if (!Number.isFinite(number)) return "-";
  if (number >= 1e9) return `${(number / 1e9).toFixed(2)} GB`;
  if (number >= 1e6) return `${(number / 1e6).toFixed(2)} MB`;
  if (number >= 1e3) return `${(number / 1e3).toFixed(2)} KB`;
  return `${number} B`;
}

/**
 * Format a chart x-axis tick; invalid values are passed through untouched.
 *
 * @param {unknown} value
 * @returns {string|unknown}
 */
export function formatTick(value) {
  const parsed = parseFloat(value);
  return Number.isFinite(parsed) ? parsed.toFixed(2) : value;
}

/**
 * Render one result metric definition to the established markup.
 *
 * @param {string} label
 * @param {unknown} value
 * @returns {string}
 */
export function metricItem(label, value) {
  return `<div class="result-metric"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd></div>`;
}

/**
 * Render metric rows inside the shared results grid.
 *
 * @param {Array<{label: string, value: unknown}>} rows
 * @returns {string}
 */
export function metricsHtml(rows) {
  return `<div class="results-grid">${rows
    .map((row) => metricItem(row.label, row.value))
    .join("")}</div>`;
}

/**
 * Metric rows for the iperf3 results panel.
 *
 * @param {object|null|undefined} result
 * @returns {Array<{label: string, value: unknown}>}
 */
export function iperf3MetricRows(result) {
  const data = result && typeof result === "object" ? result : {};
  const isTcp = String(data.protocol || "").toUpperCase() === "TCP";
  const rows = [
    { label: "Protocol", value: data.protocol },
    { label: "Duration", value: `${fmt(data.duration_seconds)} s` },
    { label: "Avg Throughput", value: `${fmt(data.avg_throughput_mbps)} Mbps` },
    { label: "Max Throughput", value: `${fmt(data.max_throughput_mbps)} Mbps` },
    { label: "Min Throughput", value: `${fmt(data.min_throughput_mbps)} Mbps` },
  ];
  if (isTcp) {
    rows.push(
      { label: "Total Bytes Sent", value: fmtBytes(data.total_bytes_sent) },
      {
        label: "Total Bytes Received",
        value: fmtBytes(data.total_bytes_received),
      },
      { label: "Retransmits", value: data.total_retransmits },
      { label: "Avg RTT", value: `${fmt(data.avg_rtt_ms)} ms` },
      { label: "Max RTT", value: `${fmt(data.max_rtt_ms)} ms` },
    );
  } else {
    rows.push(
      { label: "Total Packets", value: data.total_packets },
      { label: "Lost Packets", value: data.total_lost_packets },
      { label: "Avg Loss", value: `${fmt(data.avg_loss_percent)} %` },
      { label: "Avg Jitter", value: `${fmt(data.avg_jitter_ms)} ms` },
      { label: "Out of Order", value: data.total_out_of_order },
    );
  }
  if (data.pmtu) {
    rows.push({ label: "Path MTU", value: `${data.pmtu} bytes` });
  }
  return rows;
}

/**
 * Metric rows for ping results.
 *
 * @param {object|null|undefined} result
 * @returns {Array<{label: string, value: unknown}>}
 */
export function pingMetricRows(result) {
  const data = result && typeof result === "object" ? result : {};
  return [
    {
      label: "Packets",
      value: `${data.packets_received} / ${data.packets_transmitted}`,
    },
    { label: "Loss", value: `${fmt(data.packet_loss_percent)} %` },
    { label: "Reachable", value: data.reachable ? "Yes" : "No" },
    { label: "RTT min", value: `${fmt(data.rtt_min_ms)} ms` },
    { label: "RTT avg", value: `${fmt(data.rtt_avg_ms)} ms` },
    { label: "RTT max", value: `${fmt(data.rtt_max_ms)} ms` },
    { label: "RTT mdev", value: `${fmt(data.rtt_mdev_ms)} ms` },
  ];
}

/**
 * Metric rows for hping3 results (no RTT mdev field).
 *
 * @param {object|null|undefined} result
 * @returns {Array<{label: string, value: unknown}>}
 */
export function hping3MetricRows(result) {
  const data = result && typeof result === "object" ? result : {};
  return [
    {
      label: "Packets",
      value: `${data.packets_received} / ${data.packets_transmitted}`,
    },
    { label: "Loss", value: `${fmt(data.packet_loss_percent)} %` },
    { label: "Reachable", value: data.reachable ? "Yes" : "No" },
    { label: "RTT min", value: `${fmt(data.rtt_min_ms)} ms` },
    { label: "RTT avg", value: `${fmt(data.rtt_avg_ms)} ms` },
    { label: "RTT max", value: `${fmt(data.rtt_max_ms)} ms` },
  ];
}
