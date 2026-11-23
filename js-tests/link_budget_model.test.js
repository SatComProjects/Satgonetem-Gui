import { describe, expect, it } from "vitest";

import {
  atmosphereNote,
  budgetRows,
  budgetSummary,
  directionLabel,
  formatCapacity,
  formatDb,
  strategyLabel,
} from "../satgonetem_gui/static/link_budget_model.js";

const result = {
  capacity_kbps: 2500,
  capacity_mbps: 2.5,
  eirp_db: 44.123,
  g_over_t_db: 17.456,
  fspl_db: 178.9,
  atmospheric_db: 0.4,
  atmospheric_available: true,
  cn0_dbhz: 94.2,
  cn_db: 7.1,
  direction: "downlink",
  strategy: "shannon",
  frequency_ghz: 19,
  bandwidth_mhz: 500,
  distance_km: 1000,
  elevation_deg: 30,
};

describe("link budget formatting", () => {
  it("formats dB and capacity values", () => {
    expect(formatDb(12.345)).toBe("12.35 dB");
    expect(formatDb(null)).toBe("\u2014");
    expect(formatCapacity(2500)).toBe("2.5 Mbps");
    expect(formatCapacity(0)).toBe("0 kbps");
    expect(formatCapacity(0.5)).toBe("500 bps");
    expect(formatCapacity(2_500_000)).toBe("2.5 Gbps");
    expect(formatCapacity(null)).toBe("\u2014");
  });

  it("labels strategy and direction", () => {
    expect(strategyLabel("shannon")).toBe("Shannon");
    expect(strategyLabel("modcod")).toBe("MODCOD");
    expect(strategyLabel("other")).toBe("other");
    expect(directionLabel("downlink")).toBe("Downlink");
    expect(directionLabel("uplink")).toBe("Uplink");
  });
});

describe("link budget summaries", () => {
  it("summarizes the carrier and strategy", () => {
    expect(budgetSummary(result)).toBe(
      "Downlink \u00b7 19 GHz \u00b7 500 MHz \u00b7 1,000 km \u00b7 Shannon",
    );
    expect(budgetSummary(null)).toBe("\u2014");
  });

  it("builds breakdown rows", () => {
    const rows = budgetRows(result);

    expect(rows.map((row) => row.label)).toEqual([
      "Capacity",
      "EIRP",
      "G/T",
      "Free-space loss",
      "Atmospheric loss",
      "C/N\u2080",
      "C/N",
    ]);
    expect(rows[0].value).toBe("2.5 Mbps");
    expect(rows[1].value).toBe("44.12 dBW");
    expect(rows[2].value).toBe("17.46 dB/K");
    expect(rows[4].value).toBe("0.40 dB");
    expect(rows[5].value).toBe("94.20 dB-Hz");
  });

  it("reports atmospheric unavailability", () => {
    expect(atmosphereNote({ atmospheric_available: false })).toContain(
      "Atmospheric attenuation unavailable",
    );
    expect(atmosphereNote({ atmospheric_available: true })).toBe("");
  });
});
