import { describe, expect, it } from "vitest";

import {
  MAX_FAVORITES,
  filterNodes,
  nodeCountText,
  normalizeFavorites,
  sortNodes,
  toggleFavorite,
} from "../satgonetem_gui/static/nodes_model.js";

const nodes = [
  { name: "Sat2", type: "satellite", city: null },
  { name: "Sat10", type: "satellite", city: null },
  { name: "Gnd0", type: "ground_station", city: "Berlin" },
  { name: "Gnd1", type: "ground_station", city: "Oslo" },
  { name: "Gnd2", type: "ground_station", city: null },
];

describe("node filtering", () => {
  it("searches name, city, and type case-insensitively", () => {
    expect(filterNodes(nodes, { query: "berlin" }).map((n) => n.name)).toEqual([
      "Gnd0",
    ]);
    expect(filterNodes(nodes, { query: "SAT1" }).map((n) => n.name)).toEqual([
      "Sat10",
    ]);
    expect(
      filterNodes(nodes, { query: "ground_station" }).map((n) => n.name),
    ).toEqual(["Gnd0", "Gnd1", "Gnd2"]);
    expect(filterNodes(nodes, { query: "   " })).toHaveLength(nodes.length);
  });

  it("filters by type and favorites", () => {
    expect(
      filterNodes(nodes, { type: "satellite" }).map((n) => n.name),
    ).toEqual(["Sat2", "Sat10"]);
    expect(
      filterNodes(nodes, {
        favoritesOnly: true,
        favorites: ["Gnd1", "missing"],
      }).map((n) => n.name),
    ).toEqual(["Gnd1"]);
    expect(filterNodes(null, {})).toEqual([]);
  });
});

describe("node sorting", () => {
  it("sorts names numerically and cities with a name fallback", () => {
    expect(
      sortNodes(nodes, "name").map((node) => node.name),
    ).toEqual(["Gnd0", "Gnd1", "Gnd2", "Sat2", "Sat10"]);
    expect(
      sortNodes(nodes, "city").map((node) => node.name),
    ).toEqual(["Gnd0", "Gnd1", "Gnd2", "Sat2", "Sat10"]);
    expect(
      sortNodes(nodes, "type").map((node) => node.name),
    ).toEqual(["Sat2", "Sat10", "Gnd0", "Gnd1", "Gnd2"]);
    expect(sortNodes(null, "name")).toEqual([]);
  });

  it("does not mutate the input", () => {
    const original = nodes.map((node) => node.name);
    sortNodes(nodes, "name");
    expect(nodes.map((node) => node.name)).toEqual(original);
  });
});

describe("node favorites", () => {
  it("normalizes stored favorites", () => {
    expect(normalizeFavorites([" Gnd0 ", "Gnd0", "", null, 3])).toEqual([
      "Gnd0",
      "3",
    ]);
    expect(normalizeFavorites(null)).toEqual([]);
    expect(normalizeFavorites("nope")).toEqual([]);
  });

  it("toggles favorites and caps the list", () => {
    expect(toggleFavorite([], "Gnd0")).toEqual(["Gnd0"]);
    expect(toggleFavorite(["Gnd0"], "Gnd0")).toEqual([]);
    expect(toggleFavorite(["Gnd0"], " Gnd1 ")).toEqual(["Gnd0", "Gnd1"]);

    const many = Array.from({ length: MAX_FAVORITES + 5 }, (_, i) => `N${i}`);
    expect(toggleFavorite(many, "extra")).toHaveLength(MAX_FAVORITES);
    expect(toggleFavorite(many, "N0")).not.toContain("N0");
  });

  it("formats the visible/total count", () => {
    expect(nodeCountText(3, 10)).toBe("Showing 3 of 10 nodes");
    expect(nodeCountText(10, 10)).toBe("10 nodes");
    expect(nodeCountText(1, 1)).toBe("1 node");
    expect(nodeCountText(null, null)).toBe("\u2014");
  });
});
