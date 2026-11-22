import { describe, expect, it } from "vitest";

import {
  buildStationMap,
  mergeStations,
  selectedStations,
  selectionSummary,
  stationKey,
  validateStationName,
} from "../satgonetem_gui/static/ground_stations_model.js";

const presets = [
  {
    name: "alpha",
    stations: [{ index: 0, name: "Berlin" }, { index: 1, name: "Paris" }],
  },
  {
    name: "beta",
    stations: [{ index: 0, name: "Tokyo" }, { index: 1, name: "Oslo" }],
  },
];

describe("ground station selection", () => {
  it("does not collide when presets share row indexes", () => {
    const map = buildStationMap(presets);
    const selected = new Set([
      stationKey("alpha", 0),
      stationKey("beta", 0),
    ]);

    expect([...selected]).toEqual(["alpha:0", "beta:0"]);
    expect(selectedStations(selected, map).map((station) => station.name)).toEqual([
      "Berlin",
      "Tokyo",
    ]);
  });

  it("rejects station names the core parser cannot represent", () => {
    expect(validateStationName("Berlin")).toBeNull();
    expect(validateStationName("Berlin, DE")).toMatch("commas");
    expect(validateStationName('Berlin "Mitte"')).toMatch("quotes");
    expect(validateStationName("Berlin\nMitte")).toMatch("newlines");
    expect(validateStationName("   ")).toMatch("required");
  });

  it("merges pending stations across picker visits without duplicates", () => {
    const berlin = { index: 0, name: "Berlin", latitude: 52.5, longitude: 13.4, elevation_m: 34 };
    const paris = { index: 1, name: "Paris", latitude: 48.8, longitude: 2.3, elevation_m: 35 };

    expect(mergeStations([berlin], [paris])).toEqual([berlin, paris]);
    expect(mergeStations([berlin], [berlin])).toEqual([berlin]);
    expect(mergeStations(undefined, [paris])).toEqual([paris]);
  });

  it("summarizes all, some, and none for the header checkbox", () => {
    expect(selectionSummary(new Set(), "alpha", presets[0].stations)).toBe("none");
    expect(
      selectionSummary(new Set(["alpha:0"]), "alpha", presets[0].stations),
    ).toBe("some");
    expect(
      selectionSummary(
        new Set(["alpha:0", "alpha:1"]),
        "alpha",
        presets[0].stations,
      ),
    ).toBe("all");
    expect(selectionSummary(new Set(), "alpha", [])).toBe("none");
  });

  it("ignores stale selection keys", () => {
    const map = buildStationMap(presets);
    const selected = new Set(["alpha:0", "missing:9"]);

    expect(selectedStations(selected, map)).toEqual([
      { index: 0, name: "Berlin" },
    ]);
  });
});
