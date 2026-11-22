import { describe, expect, it } from "vitest";

import {
  formatCapacityKbps,
  formatLinkDelay,
  linkDirectionLabel,
  linkPeer,
  linkStateLabel,
  linkTypeLabel,
  linkWidth,
  linksForNode,
} from "../satgonetem_gui/static/links_model.js";

const links = [
  {
    src: "Sat0",
    dst: "Sat2",
    type: "InterSatelliteLink",
    direction: "ORBITAL",
    capacity_kbps: 1_000_000,
    is_active: true,
  },
  {
    src: "Gnd100",
    dst: "Sat0",
    type: "GroundStationLink",
    direction: "",
    capacity_kbps: 100_000,
    is_active: false,
  },
  {
    src: "Sat1",
    dst: "Sat3",
    type: "InterSatelliteLink",
    direction: "ADJACENT",
    capacity_kbps: 10_000,
    is_active: true,
  },
];

describe("link filtering", () => {
  it("returns links incident to one node, sorted by peer", () => {
    const result = linksForNode(links, "Sat0");

    expect(result).toHaveLength(2);
    expect(result.map((link) => linkPeer(link, "Sat0"))).toEqual([
      "Gnd100",
      "Sat2",
    ]);
  });

  it("returns no links for an isolated node", () => {
    expect(linksForNode(links, "Sat99")).toEqual([]);
  });
});

describe("link formatting", () => {
  it("formats capacity at kbps, Mbps, and Gbps scales", () => {
    expect(formatCapacityKbps(500)).toBe("500 kbps");
    expect(formatCapacityKbps(100_000)).toBe("100 Mbps");
    expect(formatCapacityKbps(1_500_000)).toBe("1.5 Gbps");
    expect(formatCapacityKbps(0)).toBe("Unknown");
    expect(formatCapacityKbps(null)).toBe("Unknown");
  });

  it("formats delay and state", () => {
    expect(formatLinkDelay(3.336)).toBe("3.34 ms");
    expect(formatLinkDelay(null)).toBe("Unknown");
    expect(linkStateLabel(true)).toBe("Active");
    expect(linkStateLabel(false)).toBe("Inactive");
  });

  it("labels link types and directions", () => {
    expect(linkTypeLabel("GroundStationLink")).toBe("GSL");
    expect(linkTypeLabel("InterSatelliteLink")).toBe("ISL");
    expect(linkDirectionLabel(links[1])).toBe("Ground");
    expect(linkDirectionLabel(links[0])).toBe("Orbital");
    expect(linkDirectionLabel(links[2])).toBe("Adjacent");
  });
});

describe("link width", () => {
  it("scales logarithmically with capacity and preserves path emphasis", () => {
    expect(linkWidth(1_000)).toBe(1);
    expect(linkWidth(100_000)).toBe(3);
    expect(linkWidth(1_000_000)).toBe(3.5);
    expect(linkWidth(null)).toBe(1);
    expect(linkWidth(100_000, true)).toBe(4);
  });
});
