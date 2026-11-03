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

export function splitCsv(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export function hostCidr(value) {
  const address = String(value || "").trim();
  return address.includes(":") ? `${address}/128` : `${address}/32`;
}

function numberList(values) {
  return splitCsv(values)
    .map((value) => Number(value))
    .filter((value) => Number.isInteger(value) && value >= 0 && value <= 65535);
}

export function buildPolicyPayload(fields) {
  const payload = {
    node: fields.node,
    family: fields.family || "ipv4",
    preset: fields.preset || "custom",
    default_inbound: fields.defaultInbound || "drop",
    allow_established: Boolean(fields.allowEstablished),
    allow_icmp: Boolean(fields.allowIcmp),
    allow_loopback: Boolean(fields.allowLoopback),
    management_sources: splitCsv(fields.managementSources),
    management_ports: numberList(fields.managementPorts),
    management_protocol: fields.managementProtocol || "tcp",
    ttc_sources: splitCsv(fields.ttcSources),
    ttc_ports: numberList(fields.ttcPorts),
    ttc_protocol: fields.ttcProtocol || "tcp",
    telemetry_sources: splitCsv(fields.telemetrySources),
    telemetry_ports: numberList(fields.telemetryPorts),
    telemetry_protocol: fields.telemetryProtocol || "udp",
    bcp38_ingress: Boolean(fields.bcp38),
    bcp38_egress_cidrs: splitCsv(fields.bcp38Egress),
    rate_limits: [],
    connection_limits: [],
    ingress_policing: [],
    dscp_marks: [],
  };

  if (fields.rateEnabled) {
    payload.rate_limits.push({
      protocol: fields.rateProtocol || "tcp",
      port: Number(fields.ratePort) || 0,
      source_cidr: fields.rateSource || "0.0.0.0/0",
      packets_per_second: Math.max(1, Number(fields.ratePps) || 100),
      burst: Math.max(1, Number(fields.rateBurst) || 200),
      syn_only: Boolean(fields.rateSyn),
    });
  }
  if (fields.connEnabled) {
    payload.connection_limits.push({
      port: Number(fields.connPort) || 0,
      source_cidr: fields.connSource || "0.0.0.0/0",
      max_connections: Math.max(1, Number(fields.connMax) || 20),
    });
  }
  if (fields.ingressEnabled && fields.ingressInterface) {
    payload.ingress_policing.push({
      interface: fields.ingressInterface,
      protocol: fields.ingressProtocol || "tcp",
      port: Number(fields.ingressPort) || 0,
      rate_kbps: Math.max(1, Number(fields.ingressRate) || 1000),
      burst_kb: Math.max(1, Number(fields.ingressBurst) || 32),
    });
  }
  if (fields.dscpEnabled) {
    payload.dscp_marks.push({
      protocol: fields.dscpProtocol || "udp",
      port: Number(fields.dscpPort) || 0,
      dscp: Math.min(63, Math.max(0, Number(fields.dscp) || 0)),
    });
  }
  return payload;
}

export function buildMitigationPolicy({ node, attackerIp, protocol, port, synOnly }) {
  const tcp = protocol === "tcp";
  return {
    node,
    family: String(attackerIp || "").includes(":") ? "ipv6" : "ipv4",
    preset: "ddos-mitigation",
    default_inbound: "accept",
    allow_established: true,
    allow_icmp: false,
    allow_loopback: true,
    rate_limits: [
      {
        protocol,
        port: Number(port) || 0,
        source_cidr: hostCidr(attackerIp),
        packets_per_second: 100,
        burst: 200,
        syn_only: tcp && Boolean(synOnly),
      },
    ],
    connection_limits: tcp
      ? [
          {
            port: Number(port) || 0,
            source_cidr: hostCidr(attackerIp),
            max_connections: 10,
          },
        ]
      : [],
  };
}
