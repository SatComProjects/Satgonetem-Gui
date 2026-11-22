import { describe, expect, it } from "vitest";

import {
  formatDelay,
  formatDistance,
  linkKey,
  pathChain,
  pathLinkKeys,
  pathLinkTypeLabel,
  pathRows,
  pathSummary,
} from "../satgonetem_gui/static/path_model.js";

const path = {
  src: "Gnd100",
  dst: "Sat42",
  found: true,
  node_count: 3,
  total_distance_km: 5_000,
  total_delay_ms: 16.68,
  routing_method: "static",
  routing_initiated: false,
  note: "Computed over the current routing graph.",
  hops: [
    {
      source: "Gnd100",
      target: "Sat28",
      type: "GroundStationLink",
      direction: null,
      distance_km: 1_000,
      delay_ms: 3.34,
      cumulative_distance_km: 1_000,
      cumulative_delay_ms: 3.34,
    },
    {
      source: "Sat28",
      target: "Sat42",
      type: "InterSatelliteLink",
      direction: "ORBITAL",
      distance_km: 4_000,
      delay_ms: 13.34,
      cumulative_distance_km: 5_000,
      cumulative_delay_ms: 16.68,
    },
  ],
};

describe("path link identity", () => {
  it("canonicalizes an undirected link", () => {
    expect(linkKey("Sat1", "Sat2")).toBe("Sat1|Sat2");
    expect(linkKey("Sat2", "Sat1")).toBe("Sat1|Sat2");
  });

  it("builds the set used to highlight globe links", () => {
    expect([...pathLinkKeys(path.hops)]).toEqual([
      "Gnd100|Sat28",
      "Sat28|Sat42",
    ]);
  });
});

describe("path formatting", () => {
  it("formats distances and delays", () => {
    expect(formatDistance(1_000.04)).toBe("1000 km");
    expect(formatDistance(null)).toBe("-");
    expect(formatDelay(16.684)).toBe("16.68 ms");
    expect(formatDelay(undefined)).toBe("-");
  });

  it("labels link types", () => {
    expect(pathLinkTypeLabel("GroundStationLink")).toBe("GSL");
    expect(pathLinkTypeLabel("InterSatelliteLink")).toBe("ISL");
    expect(pathLinkTypeLabel("UserTerminalLink")).toBe("UT");
    expect(pathLinkTypeLabel(null)).toBe("-");
  });

  it("builds the hop table rows", () => {
    const rows = pathRows(path);

    expect(rows).toHaveLength(2);
    expect(rows[0].link).toBe("Gnd100 \u2192 Sat28");
    expect(rows[0].type).toBe("GSL");
    expect(rows[1].type).toBe("ISL");
    expect(rows[1].cumulativeDistance).toBe("5000 km");
    expect(rows[1].cumulativeDelay).toBe("16.68 ms");
  });
});

describe("path summary", () => {
  it("describes a found path", () => {
    expect(pathSummary(path)).toContain("3 nodes");
    expect(pathSummary(path)).toContain("static");
    expect(pathSummary(path)).toContain("routing not applied");
  });

  it("describes a missing path", () => {
    expect(
      pathSummary({ src: "Gnd100", dst: "Sat42", found: false }),
    ).toBe("No path found from Gnd100 to Sat42.");
  });

  it("builds a copyable chain", () => {
    expect(pathChain(path)).toBe("Gnd100 \u2192 Sat28 \u2192 Sat42");
    expect(pathChain({ src: "Gnd100", dst: "Sat42", hops: [] })).toBe(
      "Gnd100 \u2192 Sat42",
    );
  });
});
