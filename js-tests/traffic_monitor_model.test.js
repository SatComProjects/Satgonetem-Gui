import { describe, expect, it } from "vitest";

import {
  MAX_SAMPLES,
  appendSample,
  formatBps,
  monitorSummary,
  sampleFromUsage,
  samplesToCsv,
  samplesToJson,
} from "../satgonetem_gui/static/traffic_monitor_model.js";

const links = [
  {
    src: "Sat0",
    dst: "Sat1",
    type: "InterSatelliteLink",
    delay_ms: 1.2,
    capacity_kbps: 100000,
    loss_percent: 0.5,
    jitter_ms: 3,
  },
  {
    src: "Gnd0",
    dst: "Sat0",
    type: "GroundStationLink",
    delay_ms: 4.2,
    capacity_kbps: 50000,
    loss_percent: 0,
    jitter_ms: 0,
  },
];

const usage = {
  ok: true,
  available: true,
  sampled_at: "2026-01-01T00:00:00Z",
  note: "",
  links: [
    { src: "Sat0", dst: "Sat1", value_bps: 1_000_000, capacity_kbps: 100000 },
    { src: "Gnd0", dst: "Sat0", value_bps: 500_000, capacity_kbps: 50000 },
  ],
};

const status = { current_step: 7, current_time: "2026-01-01T00:00:05Z" };

describe("traffic monitor samples", () => {
  it("aggregates links, configured metrics, and node totals", () => {
    const sample = sampleFromUsage(usage, links, status, 1000);

    expect(sample.available).toBe(true);
    expect(sample.step).toBe(7);
    expect(sample.total_bps).toBe(1_500_000);
    expect(sample.active_links).toBe(2);
    expect(sample.links[0].delay_ms).toBe(1.2);
    expect(sample.links[1].loss_percent).toBe(0);
    expect(sample.links[0].utilization).toBeCloseTo(1, 5);
    expect(sample.nodes.map((node) => node.name)).toEqual(["Sat0", "Sat1", "Gnd0"]);
    expect(sample.nodes[0].value_bps).toBe(1_500_000);
  });

  it("defaults missing metrics and tolerates empty usage", () => {
    const sample = sampleFromUsage(
      {
        available: true,
        links: [{ src: "Sat0", dst: "Sat1", value_bps: "bad" }],
      },
      null,
      null,
      5,
    );

    expect(sample.links[0].value_bps).toBe(0);
    expect(sample.links[0].capacity_kbps).toBe(0);
    expect(sample.links[0].delay_ms).toBe(0);
    expect(sample.step).toBeNull();
    expect(sample.total_bps).toBe(0);
  });

  it("reports unavailable usage without fabricating traffic", () => {
    const sample = sampleFromUsage(
      { available: false, note: "Containers stopped", links: [] },
      links,
      status,
      10,
    );

    expect(sample.available).toBe(false);
    expect(sample.note).toBe("Containers stopped");
    expect(sample.total_bps).toBe(0);
    expect(sample.links).toEqual([]);
  });

  it("caps the retained ring", () => {
    let samples = [];
    for (let index = 0; index < MAX_SAMPLES + 5; index += 1) {
      samples = appendSample(
        samples,
        sampleFromUsage(usage, links, status, index),
      );
    }

    expect(samples).toHaveLength(MAX_SAMPLES);
    expect(samples[0].timestamp).toBe(5);
  });
});

describe("traffic monitor formatting and export", () => {
  it("formats bit rates and the summary", () => {
    expect(formatBps(1_500_000)).toBe("1.5 Mbps");
    expect(formatBps(0)).toBe("0 bps");
    expect(formatBps(null)).toBe("\u2014");
    expect(monitorSummary(null)).toBe("\u2014");
    const sample = sampleFromUsage(usage, links, status, 1000);
    expect(monitorSummary(sample, 3)).toContain("step 7");
    expect(monitorSummary(sample, 3)).toContain("3 samples");
  });

  it("serializes per-link CSV rows with quoting", () => {
    const sample = sampleFromUsage(
      {
        ...usage,
        links: [{ src: 'Sat"0"', dst: "Gnd,0", value_bps: 10 }],
      },
      links,
      status,
      1000,
    );

    const csv = samplesToCsv([sample]);

    expect(csv.split("\n")[0]).toBe(
      "timestamp,step,sim_time,total_bps,active_links,src,dst,value_bps,utilization,delay_ms,loss_percent,jitter_ms",
    );
    expect(csv).toContain('"Sat""0"""');
    expect(csv).toContain('"Gnd,0"');
  });

  it("serializes JSON with a version and samples", () => {
    const sample = sampleFromUsage(usage, links, status, 1000);
    const payload = JSON.parse(samplesToJson([sample]));

    expect(payload.version).toBe(1);
    expect(payload.samples).toHaveLength(1);
    expect(payload.samples[0].total_bps).toBe(1_500_000);
  });
});
