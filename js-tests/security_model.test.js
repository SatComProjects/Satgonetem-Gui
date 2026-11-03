import { describe, expect, it } from "vitest";

import {
  averageMbps,
  buildDdosPlan,
  buildFloodFlow,
  buildIperf3Flow,
  buildSpoofFlow,
  splitThroughput,
  summarizeDdos,
  throughputPoints,
} from "../satgonetem_gui/static/security_model.js";

describe("security model", () => {
  it("builds a bounded iperf3 baseline", () => {
    expect(buildIperf3Flow({ src: "Gnd0", dst: "Gnd1", duration: "20" })).toEqual({
      src: "Gnd0",
      dst: "Gnd1",
      protocol: "TCP",
      duration: 20,
      interval: 1,
      congestion_control: "bbr",
    });
  });

  it("builds a TCP SYN flood with the expected flags", () => {
    expect(
      buildFloodFlow({
        src: "Gnd2",
        dst: "Gnd1",
        protocol: "tcp",
        rate: "fast",
      }),
    ).toMatchObject({
      proto: "tcp",
      dport: 5201,
      rate_type: "fast",
      flags: ["S"],
    });
  });

  it("does not send TCP flags for a UDP flood", () => {
    const flow = buildFloodFlow({
      src: "Gnd2",
      dst: "Gnd1",
      protocol: "udp",
      rate: "flood",
    });

    expect(flow.flags).toEqual([]);
    expect(flow.rate_type).toBe("flood");
  });

  it("builds a spoofed SYN flow", () => {
    expect(
      buildSpoofFlow({
        src: "Gnd2",
        dst: "Gnd1",
        spoofSrc: "10.0.0.7",
        count: "12",
        flags: "SA",
      }),
    ).toMatchObject({
      proto: "tcp",
      flags: ["S", "A"],
      spoof_src: "10.0.0.7",
      count: 12,
    });
  });

  it("extracts throughput points from iperf3 intervals", () => {
    const points = throughputPoints([
      { t: 1, sum: { bits_per_second: 5_000_000 } },
      { t: 2, sum: { bits_per_second: 2_500_000 } },
      { t: 3, sum: {} },
      { t: 4, sum: { bits_per_second: 1_000_000 } },
    ]);

    expect(points).toEqual([
      { t: 1, mbps: 5 },
      { t: 2, mbps: 2.5 },
      { t: 4, mbps: 1 },
    ]);
  });

  it("splits baseline and attack windows", () => {
    const points = [
      { t: 1, mbps: 10 },
      { t: 2, mbps: 9 },
      { t: 4, mbps: 2 },
      { t: 5, mbps: 1 },
    ];

    const split = splitThroughput(points, 3);

    expect(split.baseline).toHaveLength(2);
    expect(split.attack).toHaveLength(2);
    expect(averageMbps(split.baseline)).toBe(9.5);
    expect(averageMbps(split.attack)).toBe(1.5);
  });

  it("summarizes the throughput drop", () => {
    const summary = summarizeDdos(
      [
        { t: 1, mbps: 10 },
        { t: 2, mbps: 10 },
        { t: 4, mbps: 2 },
        { t: 5, mbps: 2 },
      ],
      3,
    );

    expect(summary.baseline).toBe(10);
    expect(summary.attack).toBe(2);
    expect(summary.dropPercent).toBe(80);
  });

  it("keeps the attack window inside the baseline", () => {
    const plan = buildDdosPlan({ baselineSec: 5, attackSec: 2 });
    expect(plan.attackStart).toBe(3);
    expect(plan.attackStart + 1).toBeLessThan(plan.baselineSec);
  });
});
