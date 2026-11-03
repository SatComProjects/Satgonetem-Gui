/** Pure helpers for the Space Security Lab. */

export function buildIperf3Flow({ src, dst, duration = 15 }) {
  return {
    src,
    dst,
    protocol: "TCP",
    duration: Number(duration) || 15,
    interval: 1,
    congestion_control: "bbr",
  };
}

export function buildFloodFlow({ src, dst, protocol = "udp", rate = "flood" }) {
  const proto = ["tcp", "udp", "icmp"].includes(protocol) ? protocol : "udp";
  return {
    src,
    dst,
    proto,
    dport: proto === "icmp" ? 0 : 5201,
    count: 500000,
    size: 0,
    rate_type: ["fast", "faster", "flood"].includes(rate) ? rate : "flood",
    flags: proto === "tcp" ? ["S"] : [],
    spoof_src: null,
  };
}

export function buildSpoofFlow({ src, dst, spoofSrc, count = 20, flags = "S" }) {
  return {
    src,
    dst,
    proto: "tcp",
    dport: 5201,
    count: Number(count) || 20,
    rate_type: "fast",
    flags: String(flags || "S").split(""),
    spoof_src: spoofSrc,
  };
}

export function throughputPoints(intervals) {
  if (!Array.isArray(intervals)) return [];
  const points = [];
  for (const entry of intervals) {
    const time = Number(entry?.t);
    const bits = Number(entry?.sum?.bits_per_second);
    if (!Number.isFinite(time) || !Number.isFinite(bits)) continue;
    points.push({ t: time, mbps: bits / 1_000_000 });
  }
  return points;
}

export function splitThroughput(points, attackStart) {
  const start = Number(attackStart) || 0;
  return {
    baseline: points.filter((point) => point.t < start),
    attack: points.filter((point) => point.t >= start),
  };
}

export function averageMbps(points) {
  if (!Array.isArray(points) || points.length === 0) return null;
  return points.reduce((sum, point) => sum + point.mbps, 0) / points.length;
}

export function summarizeDdos(points, attackStart) {
  const split = splitThroughput(points, attackStart);
  const baseline = averageMbps(split.baseline);
  const attack = averageMbps(split.attack);
  let dropPercent = null;
  if (baseline && attack !== null && baseline > 0) {
    dropPercent = ((baseline - attack) / baseline) * 100;
  }
  return { baseline, attack, dropPercent };
}

export function buildDdosPlan(options) {
  const requestedBaseline = Math.max(5, Number(options.baselineSec) || 15);
  const attackSec = Math.max(2, Number(options.attackSec) || 8);
  const attackStart = Math.min(3, Math.max(1, requestedBaseline - 2));
  const baselineSec = Math.max(
    requestedBaseline,
    attackStart + attackSec + 2,
  );
  return {
    baselineSec,
    attackSec,
    attackStart,
    protocol: options.protocol || "udp",
    rate: options.rate || "flood",
  };
}
