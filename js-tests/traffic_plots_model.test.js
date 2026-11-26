import { describe, expect, it } from "vitest";

import {
  buildHping3Series,
  buildIperf3Series,
  fmt,
  fmtBytes,
  formatTick,
  hping3MetricRows,
  iperf3MetricRows,
  metricItem,
  metricsHtml,
  pingMetricRows,
} from "../satgonetem_gui/static/traffic_plots_model.js";

const tcpResult = {
  protocol: "TCP",
  duration_seconds: 10,
  avg_throughput_mbps: 120.5,
  max_throughput_mbps: 150,
  min_throughput_mbps: 90,
  total_bytes_sent: 1_500_000,
  total_bytes_received: 500,
  total_retransmits: 4,
  avg_rtt_ms: 18.2,
  max_rtt_ms: 25,
  pmtu: 1500,
  intervals: [
    {
      sum: { seconds: 1, bits_per_second: 100_000_000, bytes: 12_500_000 },
      streams: [
        {
          bits_per_second: 100_000_000,
          snd_cwnd: 204_800,
          rtt: 18_000,
          retransmits: 1,
        },
      ],
    },
    {
      sum: { seconds: 2, bits_per_second: 150_000_000, bytes: 37_500_000 },
      streams: [
        {
          bits_per_second: 90_000_000,
          snd_cwnd: 102_400,
          rtt: 20_000,
          retransmits: 2,
        },
        {
          bits_per_second: 60_000_000,
          snd_cwnd: 51_200,
          rtt: 22_000,
          retransmits: 0,
        },
      ],
    },
  ],
};

describe("iperf3 series extraction", () => {
  it("derives interval, cumulative, and per-flow TCP series", () => {
    const series = buildIperf3Series(tcpResult);

    expect(series.isTcp).toBe(true);
    expect(series.isUdp).toBe(false);
    expect(series.streamCount).toBe(2);
    expect(series.times).toEqual([1, 3]);
    expect(series.throughput).toEqual([100, 150]);
    expect(series.cumulativeBits).toEqual([100, 400]);
    expect(series.cwnd).toEqual([200, 100]);
    expect(series.rtt).toEqual([18, 20]);
    expect(series.aux).toEqual([1, 2]);
    expect(series.perThroughput).toEqual([
      [100, 90],
      [null, 60],
    ]);
    expect(series.perCwnd).toEqual([
      [200, 100],
      [null, 50],
    ]);
    expect(series.perRtt).toEqual([
      [18, 20],
      [null, 22],
    ]);
    expect(series.perAux).toEqual([
      [1, 2],
      [null, 0],
    ]);
    expect(series.jitter).toEqual([]);
  });

  it("derives UDP loss and jitter series from sums and streams", () => {
    const series = buildIperf3Series({
      protocol: "UDP",
      intervals: [
        {
          sum: {
            seconds: 1,
            bits_per_second: 50_000_000,
            bytes: 6_250_000,
            lost_percent: 5,
            jitter_ms: 0.5,
          },
          streams: [
            {
              bits_per_second: 40_000_000,
              jitter_ms: 0.6,
              lost_packets: 2,
              packets: 100,
            },
          ],
        },
        {
          sum: {
            end: 4,
            start: 2,
            bits_per_second: 70_000_000,
            lost_packets: 3,
            packets: 50,
          },
          streams: [{ bits_per_second: 60_000_000, jitter_ms: 0.4 }],
        },
      ],
    });

    expect(series.isUdp).toBe(true);
    expect(series.times).toEqual([1, 3]);
    expect(series.throughput).toEqual([50, 70]);
    expect(series.cumulativeBits).toEqual([50, 50]);
    expect(series.aux).toEqual([5, 6]);
    expect(series.jitter).toEqual([0.5, 0.4]);
    expect(series.perThroughput).toEqual([[40, 60]]);
    expect(series.perJitter).toEqual([[0.6, 0.4]]);
    expect(series.perAux).toEqual([[2, null]]);
  });

  it("keeps NaN and Infinity out of every series", () => {
    const series = buildIperf3Series({
      protocol: "TCP",
      intervals: [
        {
          sum: { seconds: Infinity, bits_per_second: Infinity, bytes: NaN },
          streams: [
            {
              bits_per_second: "oops",
              snd_cwnd: Infinity,
              rtt: -Infinity,
              retransmits: "bad",
            },
          ],
        },
        { sum: { seconds: 1, bits_per_second: NaN, bytes: "NaN" } },
      ],
    });

    expect(series.times).toEqual([1, 2]);
    expect(series.throughput).toEqual([0, 0]);
    expect(series.cumulativeBits).toEqual([0, 0]);
    expect(series.cwnd).toEqual([null, null]);
    expect(series.rtt).toEqual([null, null]);
    expect(series.aux).toEqual([0, 0]);
    expect(series.perThroughput).toEqual([[null, null]]);
    expect(series.perAux).toEqual([[null, null]]);
    for (const value of [
      ...series.times,
      ...series.throughput,
      ...series.cumulativeBits,
      ...series.aux,
    ]) {
      expect(Number.isFinite(value)).toBe(true);
    }
  });

  it("treats a missing payload as an empty UDP series", () => {
    const series = buildIperf3Series(undefined);

    expect(series.isTcp).toBe(false);
    expect(series.streamCount).toBe(0);
    expect(series.times).toEqual([]);
    expect(series.throughput).toEqual([]);
    expect(series.cumulativeBits).toEqual([]);
  });
});

describe("hping3 series extraction", () => {
  it("builds string labels and finite-optional point arrays", () => {
    const series = buildHping3Series({
      seq: [1, 2, 3],
      rtt_ms: [10.5, "bad", null],
      cumulative_mbit: [0.1, 0.2],
    });

    expect(series.labels).toEqual(["1", "2", "3"]);
    expect(series.rtt).toEqual([10.5, null, null]);
    expect(series.cumulativeMbit).toEqual([0.1, 0.2]);
  });

  it("defaults missing arrays to empty series", () => {
    expect(buildHping3Series(null)).toEqual({
      labels: [],
      rtt: [],
      cumulativeMbit: [],
    });
  });
});

describe("metric rows", () => {
  it("renders the TCP iperf3 rows in their established order", () => {
    expect(iperf3MetricRows(tcpResult)).toEqual([
      { label: "Protocol", value: "TCP" },
      { label: "Duration", value: "10.00 s" },
      { label: "Avg Throughput", value: "120.50 Mbps" },
      { label: "Max Throughput", value: "150.00 Mbps" },
      { label: "Min Throughput", value: "90.00 Mbps" },
      { label: "Total Bytes Sent", value: "1.50 MB" },
      { label: "Total Bytes Received", value: "500 B" },
      { label: "Retransmits", value: 4 },
      { label: "Avg RTT", value: "18.20 ms" },
      { label: "Max RTT", value: "25.00 ms" },
      { label: "Path MTU", value: "1500 bytes" },
    ]);
  });

  it("uses the UDP iperf3 rows and omits the path MTU when absent", () => {
    const rows = iperf3MetricRows({
      protocol: "UDP",
      duration_seconds: 5,
      total_packets: 100,
      total_lost_packets: 2,
      avg_loss_percent: 2,
      avg_jitter_ms: 0.25,
      total_out_of_order: 1,
    });

    expect(rows.map((row) => row.label)).toEqual([
      "Protocol",
      "Duration",
      "Avg Throughput",
      "Max Throughput",
      "Min Throughput",
      "Total Packets",
      "Lost Packets",
      "Avg Loss",
      "Avg Jitter",
      "Out of Order",
    ]);
    expect(rows.find((row) => row.label === "Avg Loss").value).toBe("2.00 %");
  });

  it("builds ping rows including RTT mdev", () => {
    const rows = pingMetricRows({
      packets_received: 9,
      packets_transmitted: 10,
      packet_loss_percent: 10,
      reachable: true,
      rtt_min_ms: 21,
      rtt_avg_ms: 24.5,
      rtt_max_ms: 30,
      rtt_mdev_ms: 3,
    });

    expect(rows).toEqual([
      { label: "Packets", value: "9 / 10" },
      { label: "Loss", value: "10.00 %" },
      { label: "Reachable", value: "Yes" },
      { label: "RTT min", value: "21.00 ms" },
      { label: "RTT avg", value: "24.50 ms" },
      { label: "RTT max", value: "30.00 ms" },
      { label: "RTT mdev", value: "3.00 ms" },
    ]);
  });

  it("builds hping3 rows without an RTT mdev field", () => {
    const rows = hping3MetricRows({
      packets_received: 8,
      packets_transmitted: 10,
      packet_loss_percent: 20,
      reachable: false,
      rtt_min_ms: 21,
      rtt_avg_ms: 24.5,
      rtt_max_ms: 30,
    });

    expect(rows.map((row) => row.label)).toEqual([
      "Packets",
      "Loss",
      "Reachable",
      "RTT min",
      "RTT avg",
      "RTT max",
    ]);
    expect(rows[2].value).toBe("No");
  });

  it("escapes labels and values inside the results grid", () => {
    expect(metricItem("A <b>", "x & y")).toBe(
      '<div class="result-metric"><dt>A &lt;b&gt;</dt><dd>x &amp; y</dd></div>',
    );
    expect(metricsHtml([{ label: "one", value: 1 }, { label: "two", value: null }])).toBe(
      '<div class="results-grid"><div class="result-metric"><dt>one</dt><dd>1</dd></div><div class="result-metric"><dt>two</dt><dd>null</dd></div></div>',
    );
  });
});

describe("formatting helpers", () => {
  it("formats finite numbers and preserves the historical fallbacks", () => {
    expect(fmt(1.234)).toBe("1.23");
    expect(fmt(0)).toBe("0.00");
    expect(fmt(null)).toBe("-");
    expect(fmt(undefined)).toBe("-");
    expect(fmt(Number.NaN)).toBe("-");
    expect(fmt(Number.POSITIVE_INFINITY)).toBe("Infinity");
    expect(fmt("bad")).toBe("bad");
  });

  it("formats byte counts with unit thresholds", () => {
    expect(fmtBytes(0)).toBe("0 B");
    expect(fmtBytes(500)).toBe("500 B");
    expect(fmtBytes(1500)).toBe("1.50 KB");
    expect(fmtBytes(2_000_000)).toBe("2.00 MB");
    expect(fmtBytes(3_000_000_000)).toBe("3.00 GB");
    expect(fmtBytes(null)).toBe("-");
    expect(fmtBytes(Number.POSITIVE_INFINITY)).toBe("-");
  });

  it("formats chart x-axis ticks and passes non-numeric values through", () => {
    expect(formatTick("2")).toBe("2.00");
    expect(formatTick(1.234)).toBe("1.23");
    expect(formatTick("text")).toBe("text");
  });
});
