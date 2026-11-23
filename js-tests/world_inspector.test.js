import { describe, expect, it } from "vitest";

import {
  deepLinkNode,
  linkCategory,
  nearestPeers,
  summarizeLinks,
} from "../satgonetem_gui/static/world_model.js";

describe("world inspector links", () => {
  it("classifies link types", () => {
    expect(linkCategory({ type: "GroundStationLink" })).toBe("gsl");
    expect(linkCategory({ type: "UserTerminalLink" })).toBe("gsl");
    expect(linkCategory({ type: "InterSatelliteLink", direction: "ADJACENT" })).toBe(
      "adjacent",
    );
    expect(linkCategory({ type: "InterSatelliteLink", direction: "UP" })).toBe(
      "orbital",
    );
    expect(linkCategory(null)).toBe("orbital");
  });

  it("summarizes incident links and peers", () => {
    const links = [
      { src: "Sat0", dst: "Sat1", type: "InterSatelliteLink" },
      { src: "Gnd0", dst: "Sat0", type: "GroundStationLink" },
      { src: "Sat0", dst: "Sat2", type: "InterSatelliteLink", direction: "ADJACENT" },
      { src: "Sat1", dst: "Sat2", type: "InterSatelliteLink" },
    ];

    const summary = summarizeLinks(links, "Sat0");

    expect(summary.total).toBe(3);
    expect(summary.byCategory).toEqual({ gsl: 1, orbital: 1, adjacent: 1 });
    expect(summary.incident.map((link) => link.peer)).toEqual([
      "Sat1",
      "Gnd0",
      "Sat2",
    ]);
    expect(summarizeLinks(null, "Sat0")).toEqual({
      total: 0,
      byCategory: { gsl: 0, orbital: 0, adjacent: 0 },
      incident: [],
    });
  });
});

describe("world inspector nearest peers", () => {
  const node = {
    name: "Sat0",
    position: { latitude: 0, longitude: 0, altitude: 550 },
  };
  const nodes = [
    node,
    { name: "Sat1", position: { latitude: 0, longitude: 1, altitude: 550 } },
    { name: "Gnd0", position: { latitude: 0, longitude: 0.5, altitude: 0 } },
    { name: "SatBroken", position: { latitude: null, longitude: 0 } },
    { name: "Sat2", position: { latitude: 0, longitude: 2, altitude: 550 } },
  ];

  it("orders peers by great-circle distance and skips invalid positions", () => {
    const peers = nearestPeers(node, nodes, 3);

    expect(peers.map((peer) => peer.name)).toEqual(["Gnd0", "Sat1", "Sat2"]);
    expect(peers[0].distance_km).toBeGreaterThan(55);
    expect(peers[0].distance_km).toBeLessThan(56);
    expect(peers[2].distance_km).toBeGreaterThan(222);
    expect(peers[2].distance_km).toBeLessThan(223);
  });

  it("handles a missing selection position and empty lists", () => {
    expect(
      nearestPeers(
        { name: "Sat0", position: { latitude: null, longitude: 0 } },
        nodes,
      ),
    ).toEqual([]);
    expect(nearestPeers(node, null)).toEqual([]);
  });
});

describe("world deep link", () => {
  it("extracts and trims a node query parameter", () => {
    expect(deepLinkNode("?node=Sat12")).toBe("Sat12");
    expect(deepLinkNode("?node=%20Sat%201%20&view=globe")).toBe("Sat 1");
    expect(deepLinkNode("?node=")).toBeNull();
    expect(deepLinkNode("")).toBeNull();
    expect(deepLinkNode(null)).toBeNull();
  });
});
