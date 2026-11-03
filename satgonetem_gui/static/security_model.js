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

function clamp(value, minimum, maximum) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return minimum;
  return Math.min(maximum, Math.max(minimum, parsed));
}

export function buildFloodFlow({
  src,
  dst,
  protocol = "udp",
  rate = "flood",
  pps = 5000,
  size = 0,
  dport = 5201,
  flags = "S",
}) {
  const proto = ["tcp", "udp", "icmp"].includes(protocol) ? protocol : "udp";
  const rateType = ["fast", "faster", "flood", "interval"].includes(rate)
    ? rate
    : "flood";
  const safePps = clamp(pps, 1, 1000000);
  const interval = rateType === "interval" ? `u${Math.max(1, Math.round(1000000 / safePps))}` : "";
  const flagLetters = proto === "tcp"
    ? String(flags || "S").split("").filter((flag) => "SAFRPU".includes(flag))
    : [];
  return {
    src,
    dst,
    proto,
    dport: proto === "icmp" ? 0 : clamp(dport, 0, 65535),
    count: 500000,
    size: clamp(size, 0, 65507),
    rate_type: rateType,
    interval,
    flags: flagLetters,
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
