/** Pure aggregation and export helpers for the traffic monitor. */

export const MAX_SAMPLES = 300;
export const CSV_HEADER =
  "timestamp,step,sim_time,total_bps,active_links,src,dst,value_bps,utilization,delay_ms,loss_percent,jitter_ms";

function number(value, fallback = 0) {
  if (value === null || value === undefined || value === "") return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function linkKey(src, dst) {
  return [String(src), String(dst)].sort().join("|");
}

export function sampleFromUsage(usage, links, status, now = Date.now()) {
  const available = usage?.available !== false;
  const configured = new Map();
  for (const link of Array.isArray(links) ? links : []) {
    if (!link) continue;
    configured.set(linkKey(link.src, link.dst), link);
  }
  const nodeTotals = new Map();
  const linkRows = [];
  for (const entry of available && Array.isArray(usage?.links) ? usage.links : []) {
    if (!entry || !entry.src || !entry.dst) continue;
    const key = linkKey(entry.src, entry.dst);
    const config = configured.get(key) || {};
    const valueBps = number(entry.value_bps);
    const capacityKbps = number(
      entry.capacity_kbps !== undefined && entry.capacity_kbps !== null
        ? entry.capacity_kbps
        : config.capacity_kbps,
    );
    const utilization =
      entry.utilization !== undefined && entry.utilization !== null
        ? number(entry.utilization)
        : capacityKbps > 0
          ? (valueBps / (capacityKbps * 1000)) * 100
          : 0;
    linkRows.push({
      src: String(entry.src),
      dst: String(entry.dst),
      type: entry.type || config.type || "",
      value_bps: valueBps,
      capacity_kbps: capacityKbps,
      utilization,
      delay_ms: number(config.delay_ms),
      loss_percent: number(config.loss_percent),
      jitter_ms: number(config.jitter_ms),
    });
    nodeTotals.set(entry.src, (nodeTotals.get(entry.src) || 0) + valueBps);
    nodeTotals.set(entry.dst, (nodeTotals.get(entry.dst) || 0) + valueBps);
  }
  const nodes = [...nodeTotals.entries()]
    .map(([name, value]) => ({ name, value_bps: value }))
    .sort(
      (left, right) =>
        right.value_bps - left.value_bps || left.name.localeCompare(right.name),
    );
  return {
    timestamp: now,
    step: status?.current_step ?? null,
    sim_time: status?.current_time ?? null,
    available,
    note: usage?.note || "",
    total_bps: linkRows.reduce((total, link) => total + link.value_bps, 0),
    active_links: linkRows.length,
    links: linkRows,
    nodes,
  };
}

export function appendSample(samples, sample, max = MAX_SAMPLES) {
  if (!sample) return Array.isArray(samples) ? samples : [];
  const next = [...(Array.isArray(samples) ? samples : []), sample];
  return next.slice(-Math.max(1, max));
}

export function formatBps(value) {
  if (value === null || value === undefined || value === "") return "\u2014";
  const bps = Number(value);
  if (!Number.isFinite(bps)) return "\u2014";
  const absolute = Math.abs(bps);
  if (absolute >= 1e9) return `${(bps / 1e9).toFixed(1)} Gbps`;
  if (absolute >= 1e6) return `${(bps / 1e6).toFixed(1)} Mbps`;
  if (absolute >= 1e3) return `${(bps / 1e3).toFixed(1)} kbps`;
  return `${Math.round(bps)} bps`;
}

export function monitorSummary(sample, sampleCount = 0) {
  if (!sample) return "\u2014";
  return (
    `step ${sample.step ?? "\u2014"} \u00b7 ${sampleCount} sample${
      sampleCount === 1 ? "" : "s"
    } \u00b7 ${formatBps(sample.total_bps)} \u00b7 ${sample.active_links} link${
      sample.active_links === 1 ? "" : "s"
    }`
  );
}

function csvCell(value) {
  const text = String(value ?? "");
  if (/[",\n]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
  return text;
}

export function samplesToCsv(samples) {
  const rows = [CSV_HEADER];
  for (const sample of Array.isArray(samples) ? samples : []) {
    if (!sample) continue;
    const links = Array.isArray(sample.links) ? sample.links : [];
    if (!links.length) {
      rows.push(
        [
          sample.timestamp,
          sample.step ?? "",
          sample.sim_time ?? "",
          sample.total_bps,
          sample.active_links,
          "",
          "",
          "",
          "",
          "",
          "",
          "",
        ]
          .map(csvCell)
          .join(","),
      );
      continue;
    }
    for (const link of links) {
      rows.push(
        [
          sample.timestamp,
          sample.step ?? "",
          sample.sim_time ?? "",
          sample.total_bps,
          sample.active_links,
          link.src,
          link.dst,
          link.value_bps,
          link.utilization,
          link.delay_ms,
          link.loss_percent,
          link.jitter_ms,
        ]
          .map(csvCell)
          .join(","),
      );
    }
  }
  return `${rows.join("\n")}\n`;
}

export function samplesToJson(samples) {
  return `${JSON.stringify(
    { version: 1, samples: Array.isArray(samples) ? samples : [] },
    null,
    2,
  )}\n`;
}
