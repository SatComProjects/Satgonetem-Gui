/** Pure traffic-form payload builder. */

function numberOr(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function buildTrafficPayload(fields) {
  const tool = fields.tool || "iperf3";
  const delay = numberOr(fields.delay, 0);
  const src = fields.src || "";
  const dst = fields.dst || "";
  const payload = { src, dst, delay };
  let label = "";

  if (tool === "iperf3") {
    payload.protocol = fields.protocol || "TCP";
    payload.duration = numberOr(fields.duration, 10);
    payload.port = numberOr(fields.port, 5201);
    payload.bandwidth_mbps = numberOr(fields.bandwidthMbps, 0);
    payload.parallel = numberOr(fields.parallel, 1);
    payload.interval = numberOr(fields.interval, 1);
    if (payload.protocol === "TCP") {
      payload.congestion_control = fields.congestionControl || "bbr";
      payload.window_size = fields.windowSize || "";
      payload.bidir = Boolean(fields.bidir);
    } else {
      payload.bidir = Boolean(fields.bidirUdp);
    }
    label = `iperf3 ${src} -> ${dst} (${payload.protocol})`;
  } else if (tool === "ping") {
    payload.count = numberOr(fields.pingCount, 10);
    payload.timeout_sec = numberOr(fields.pingTimeout, 1);
    payload.interval_sec = numberOr(fields.pingInterval, 0.2);
    payload.packet_size = numberOr(fields.pingSize, 56);
    label = `ping ${src} -> ${dst} (${payload.count})`;
  } else if (tool === "hping3") {
    payload.proto = fields.hpingProto || "tcp";
    payload.dport = numberOr(fields.hpingDport, 80);
    payload.count = numberOr(fields.hpingCount, 100);
    payload.size = numberOr(fields.hpingSize, 0);
    payload.rate_type = fields.hpingRate || "interval";
    if (payload.rate_type === "interval") {
      payload.interval = fields.hpingInterval || "";
    }
    payload.flags = Array.isArray(fields.hpingFlags) ? fields.hpingFlags : [];
    label = `hping3 ${payload.proto} ${src} -> ${dst}`;
  }

  return { kind: tool, payload, label, delay };
}
