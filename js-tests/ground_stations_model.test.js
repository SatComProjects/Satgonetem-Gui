import { describe, expect, it } from "vitest";

import {
  buildStationMap,
  selectedStations,
  stationKey,
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

  it("ignores stale selection keys", () => {
    const map = buildStationMap(presets);
    const selected = new Set(["alpha:0", "missing:9"]);

    expect(selectedStations(selected, map)).toEqual([
      { index: 0, name: "Berlin" },
    ]);
  });
});
