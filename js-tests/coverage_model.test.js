import { describe, expect, it } from "vitest";

import {
  coverageClass,
  coverageNotes,
  coverageSummary,
  formatCount,
  formatCoverage,
  formatDuration,
  formatElevation,
  sortGroundStations,
} from "../satgonetem_gui/static/coverage_model.js";

describe("coverage formatting", () => {
  it("classifies coverage percentages", () => {
    expect(coverageClass(0)).toBe("none");
    expect(coverageClass(0.1)).toBe("low");
    expect(coverageClass(49.9)).toBe("low");
    expect(coverageClass(50)).toBe("fair");
    expect(coverageClass(79.9)).toBe("fair");
    expect(coverageClass(80)).toBe("good");
    expect(coverageClass(100)).toBe("good");
    expect(coverageClass(null)).toBe("unknown");
  });

  it("formats percentages, counts, durations, and elevations", () => {
    expect(formatCoverage(37.5)).toBe("37.5%");
    expect(formatCoverage(0)).toBe("0.0%");
    expect(formatCoverage(null)).toBe("\u2014");
    expect(formatCount(64_800)).toBe("64,800");
    expect(formatCount(null)).toBe("\u2014");
    expect(formatDuration(82)).toBe("82 ms");
    expect(formatDuration(1500)).toBe("1.5 s");
    expect(formatElevation(41.234)).toBe("41.2\u00b0");
    expect(formatElevation(null)).toBe("\u2014");
  });

  it("builds a snapshot summary", () => {
    expect(
      coverageSummary({
        satellites: 100,
        sampled_cells: 64_800,
        duration_ms: 82,
        cached: false,
      }),
    ).toBe("100 satellites \u00b7 64,800 cells \u00b7 82 ms");
    expect(
      coverageSummary({
        satellites: 100,
        sampled_cells: 64_800,
        duration_ms: 0,
        cached: true,
      }),
    ).toBe("100 satellites \u00b7 64,800 cells \u00b7 0 ms \u00b7 cached");
    expect(coverageSummary(null)).toBe("\u2014");
    expect(
      coverageNotes({
        shells_truncated: true,
        ground_stations_truncated: true,
      }),
    ).toBe("Shell breakdown truncated. Ground-station list truncated.");
  });
});

describe("ground station sorting", () => {
  it("puts covered stations first, then sorts by name", () => {
    const stations = [
      { name: "Oslo", covered: false },
      { name: "Berlin", covered: true },
      { name: "Accra", covered: false },
      { name: "Austin", covered: true },
    ];

    expect(sortGroundStations(stations).map((station) => station.name)).toEqual([
      "Austin",
      "Berlin",
      "Accra",
      "Oslo",
    ]);
    expect(stations.map((station) => station.name)).toEqual([
      "Oslo",
      "Berlin",
      "Accra",
      "Austin",
    ]);
    expect(sortGroundStations(null)).toEqual([]);
  });
});
