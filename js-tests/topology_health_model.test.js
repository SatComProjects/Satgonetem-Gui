import { describe, expect, it } from "vitest";

import {
  formatItemCount,
  healthSummary,
  nonEmptyChecks,
  severityLabel,
} from "../satgonetem_gui/static/topology_health_model.js";

describe("topology health formatting", () => {
  it("summarizes node/link counts and warning state", () => {
    expect(
      healthSummary({ nodes: 101, links: 200, healthy: true, checks: [] }),
    ).toBe("101 nodes \u00b7 200 links \u00b7 healthy");
    expect(
      healthSummary({
        nodes: 101,
        links: 200,
        healthy: false,
        checks: [
          { id: "zero_capacity_links", severity: "warning", count: 2 },
          { id: "isolated_nodes", severity: "info", count: 3 },
        ],
      }),
    ).toBe("101 nodes \u00b7 200 links \u00b7 1 warning");
    expect(
      healthSummary({
        nodes: 1,
        links: 0,
        healthy: false,
        checks: [
          { id: "a", severity: "warning", count: 1 },
          { id: "b", severity: "warning", count: 1 },
        ],
      }),
    ).toBe("1 node \u00b7 0 links \u00b7 2 warnings");
    expect(healthSummary(null)).toBe("\u2014");
  });

  it("labels severities and item counts", () => {
    expect(severityLabel("warning")).toBe("Warning");
    expect(severityLabel("info")).toBe("Info");
    expect(severityLabel("other")).toBe("Notice");
    expect(formatItemCount(1)).toBe("1 item");
    expect(formatItemCount(3)).toBe("3 items");
    expect(formatItemCount(null)).toBe("\u2014");
  });

  it("filters empty checks and puts warnings first", () => {
    const checks = [
      { id: "isolated_nodes", severity: "info", count: 2 },
      { id: "zero_capacity_links", severity: "warning", count: 0 },
      { id: "self_links", severity: "warning", count: 1 },
      { id: "duplicate_positions", severity: "warning", count: 1 },
    ];

    expect(nonEmptyChecks(checks).map((check) => check.id)).toEqual([
      "duplicate_positions",
      "self_links",
      "isolated_nodes",
    ]);
    expect(nonEmptyChecks(null)).toEqual([]);
  });
});
