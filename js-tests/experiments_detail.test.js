import { describe, expect, it } from "vitest";

import {
  compareTableRows,
  diffScenarioLines,
  formatBps,
  sampleSeries,
} from "../satgonetem_gui/static/experiments_model.js";

describe("experiment metrics series", () => {
  it("aggregates link traffic per sample", () => {
    const series = sampleSeries([
      {
        sim_time_s: 0,
        links: [
          { tx_bps: 100, rx_bps: 50, active: true, loss_percent: 1 },
          { tx_bps: 200, rx_bps: 150, active: false, loss_percent: 3 },
        ],
      },
      { sim_time_s: 5 },
    ]);

    expect(series).toEqual([
      {
        sim_time_s: 0,
        tx_bps: 300,
        rx_bps: 200,
        active_links: 1,
        avg_loss_percent: 2,
      },
      {
        sim_time_s: 5,
        tx_bps: 0,
        rx_bps: 0,
        active_links: 0,
        avg_loss_percent: 0,
      },
    ]);
  });

  it("ignores non-numeric link values", () => {
    const series = sampleSeries([
      {
        sim_time_s: "2",
        links: [{ tx_bps: "bad", rx_bps: 5, loss_percent: null }],
      },
    ]);

    expect(series[0].sim_time_s).toBe(2);
    expect(series[0].tx_bps).toBe(0);
    expect(series[0].rx_bps).toBe(5);
    expect(series[0].avg_loss_percent).toBe(0);
  });
});

describe("experiment formatting", () => {
  it("formats bit rates across units", () => {
    expect(formatBps(0)).toBe("0 bps");
    expect(formatBps(999)).toBe("999 bps");
    expect(formatBps(1500)).toBe("1.5 kbps");
    expect(formatBps(2_500_000)).toBe("2.5 Mbps");
    expect(formatBps(3_000_000_000)).toBe("3.0 Gbps");
    expect(formatBps(null)).toBe("\u2014");
  });

  it("builds a comparison table from run summaries", () => {
    const runs = [
      {
        name: "Alpha",
        mode: "offline",
        status: "done",
        started_at: "2026-01-01T00:00:00Z",
        summary: {
          metrics: {
            sim_time_s: 30,
            samples: 6,
            avg_tx_bps: 1500,
            max_tx_bps: 2000,
            avg_rx_bps: 1200,
            max_rx_bps: 1800,
            last_errors: ["link down"],
          },
          flows: { count: 2, errors: 1 },
          connectivity: { reachable: 4, pairs: 6 },
        },
      },
      { name: "Beta", mode: "live", status: "error", started_at: null },
    ];

    const rows = compareTableRows(runs);

    expect(rows.find((row) => row.label === "Simulation time").values).toEqual([
      "30 s",
      "\u2014",
    ]);
    expect(rows.find((row) => row.label === "Avg TX").values).toEqual([
      "1.5 kbps",
      "\u2014",
    ]);
    expect(rows.find((row) => row.label === "Flow errors").values).toEqual([
      "1",
      "\u2014",
    ]);
    expect(rows.find((row) => row.label === "Simulator errors").values).toEqual([
      "1",
      "\u2014",
    ]);
    expect(rows.find((row) => row.label === "Connectivity").values).toEqual([
      "4/6 reachable",
      "\u2014",
    ]);
    expect(rows.find((row) => row.label === "Started").values[1]).toBe("\u2014");
  });
});

describe("scenario diff", () => {
  it("marks unchanged, removed, and added lines", () => {
    const baseline = "name: A\nduration_s: 5\nshells:\n  - planes: 2\n";
    const other = "name: A\nduration_s: 10\nshells:\n  - planes: 3\n";

    const diff = diffScenarioLines(baseline, other);

    expect(diff).toEqual([
      { kind: "same", text: "name: A" },
      { kind: "remove", text: "duration_s: 5" },
      { kind: "add", text: "duration_s: 10" },
      { kind: "same", text: "shells:" },
      { kind: "remove", text: "  - planes: 2" },
      { kind: "add", text: "  - planes: 3" },
    ]);
  });

  it("falls back for very large scenarios", () => {
    const huge = Array.from({ length: 800 }, (_, index) => `line: ${index}`).join(
      "\n",
    );

    const diff = diffScenarioLines(huge, huge);

    expect(diff).toHaveLength(1);
    expect(diff[0].kind).toBe("meta");
  });
});
