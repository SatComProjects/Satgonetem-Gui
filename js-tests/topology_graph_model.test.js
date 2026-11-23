import { describe, expect, it } from "vitest";

import {
  edgeTooltip,
  filterTopology,
  layoutTopology,
  partitionTopology,
  shellOptions,
} from "../satgonetem_gui/static/topology_graph_model.js";

const nodes = [
  { name: "Sat0", type: "satellite", shell: "LEO", city: null },
  { name: "Sat1", type: "satellite", shell: "LEO", city: null },
  { name: "Sat2", type: "satellite", shell: "MEO", city: null },
  { name: "Gnd0", type: "ground_station", shell: null, city: "Berlin" },
  { name: "Gnd1", type: "ground_station", shell: null, city: null },
];

const links = [
  { src: "Sat0", dst: "Sat1", type: "InterSatelliteLink", delay_ms: 1.2 },
  { src: "Sat0", dst: "Gnd0", type: "GroundStationLink", delay_ms: 4.2 },
  { src: "Sat2", dst: "Gnd1", type: "GroundStationLink", delay_ms: 7.5 },
];

describe("topology filters", () => {
  it("lists shells and keeps stations when filtering by shell", () => {
    expect(shellOptions(nodes)).toEqual(["LEO", "MEO"]);

    const filtered = filterTopology(nodes, links, { shell: "LEO" });

    expect(filtered.nodes.map((node) => node.name)).toEqual([
      "Sat0",
      "Sat1",
      "Gnd0",
      "Gnd1",
    ]);
    expect(filtered.links.map((link) => link.dst)).toEqual(["Sat1", "Gnd0"]);
  });

  it("composes type and search filters case-insensitively", () => {
    const stations = filterTopology(nodes, links, { type: "ground_station" });
    expect(stations.nodes.map((node) => node.name)).toEqual(["Gnd0", "Gnd1"]);
    expect(stations.links).toEqual([]);

    const search = filterTopology(nodes, links, { query: "BERLIN" });
    expect(search.nodes.map((node) => node.name)).toEqual(["Gnd0"]);

    const shellSearch = filterTopology(nodes, links, { query: "leo" });
    expect(shellSearch.nodes.map((node) => node.name)).toEqual(["Sat0", "Sat1"]);
  });

  it("tolerates empty input", () => {
    expect(filterTopology(null, null, {})).toEqual({ nodes: [], links: [] });
  });
});

describe("topology layout", () => {
  it("is deterministic and stays in bounds", () => {
    const forward = layoutTopology(nodes, { width: 1000, height: 700 });
    const reverse = layoutTopology([...nodes].reverse(), {
      width: 1000,
      height: 700,
    });

    expect(forward).toEqual(reverse);
    for (const point of Object.values(forward)) {
      expect(point.x).toBeGreaterThanOrEqual(0);
      expect(point.x).toBeLessThanOrEqual(1000);
      expect(point.y).toBeGreaterThanOrEqual(0);
      expect(point.y).toBeLessThanOrEqual(700);
    }
    expect(layoutTopology([], {})).toEqual({});
  });

  it("puts each shell on a stable ring and stations near the center", () => {
    const positions = layoutTopology(nodes, { width: 1000, height: 700 });
    const center = { x: 500, y: 350 };
    const distance = (point) =>
      Math.hypot(point.x - center.x, point.y - center.y);

    expect(distance(positions.Sat0)).toBeCloseTo(distance(positions.Sat1), 5);
    expect(distance(positions.Sat2)).toBeLessThan(distance(positions.Sat0));
    expect(distance(positions.Gnd0)).toBeLessThan(distance(positions.Sat2));
    expect(distance(positions.Gnd1)).toBeLessThan(distance(positions.Sat0));
  });
});

describe("topology partitions", () => {
  it("finds components and isolated nodes deterministically", () => {
    const withIsolated = [
      ...nodes,
      { name: "Gnd2", type: "ground_station", shell: null, city: null },
    ];
    const partitions = partitionTopology(withIsolated, links);

    expect(partitions.components.map((component) => component.nodes)).toEqual([
      ["Gnd0", "Sat0", "Sat1"],
      ["Gnd1", "Sat2"],
      ["Gnd2"],
    ]);
    expect(partitions.componentByNode.Sat0).toBe(0);
    expect(partitions.componentByNode.Gnd2).toBe(2);
    expect(partitions.count).toBe(3);
    expect(partitionTopology([], []).components).toEqual([]);
  });
});

describe("topology edge tooltips", () => {
  it("includes delay, capacity, loss, and jitter", () => {
    const tooltip = edgeTooltip({
      delay_ms: 4.2,
      capacity_kbps: 100000,
      loss_percent: 0.5,
      jitter_ms: 10,
    });

    expect(tooltip).toContain("delay 4.2 ms");
    expect(tooltip).toContain("capacity 100000 kbps");
    expect(tooltip).toContain("loss 0.5%");
    expect(tooltip).toContain("jitter 10 ms");
    expect(edgeTooltip(null)).toBe("");
  });
});
