import { describe, expect, it } from "vitest";

import { buildTrafficPayload } from "../satgonetem_gui/static/traffic_model.js";

describe("traffic payload builder", () => {
  it("builds an iperf3 TCP payload", () => {
    const result = buildTrafficPayload({
      tool: "iperf3",
      src: "Sat0",
      dst: "Sat1",
      delay: "0",
      protocol: "TCP",
      duration: "10",
      port: "5201",
      bandwidthMbps: "0",
      parallel: "1",
      interval: "1",
      congestionControl: "bbr",
      windowSize: "",
      bidir: true,
    });

    expect(result.kind).toBe("iperf3");
    expect(result.payload).toMatchObject({
      src: "Sat0",
      dst: "Sat1",
      duration: 10,
      bidir: true,
      congestion_control: "bbr",
    });
  });

  it("builds a ping payload", () => {
    const result = buildTrafficPayload({
      tool: "ping",
      src: "Sat0",
      dst: "Gnd9",
      pingCount: "3",
      pingTimeout: "1",
      pingInterval: "0.2",
      pingSize: "56",
    });

    expect(result.kind).toBe("ping");
    expect(result.payload).toMatchObject({
      count: 3,
      timeout_sec: 1,
      interval_sec: 0.2,
      packet_size: 56,
    });
    expect(result.label).toContain("ping Sat0 -> Gnd9");
  });

  it("builds an hping3 payload", () => {
    const result = buildTrafficPayload({
      tool: "hping3",
      src: "Sat0",
      dst: "Sat1",
      hpingProto: "udp",
      hpingDport: "80",
      hpingCount: "5",
      hpingSize: "64",
      hpingRate: "interval",
      hpingInterval: "0.5",
      hpingFlags: ["-S"],
    });

    expect(result.kind).toBe("hping3");
    expect(result.payload).toMatchObject({
      proto: "udp",
      dport: 80,
      count: 5,
      size: 64,
      interval: "0.5",
      flags: ["-S"],
    });
  });
});
