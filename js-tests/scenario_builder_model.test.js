import { describe, expect, it } from "vitest";

import {
  addShell,
  addStation,
  buildScenarioYaml,
  defaultBuilderState,
  removeShell,
  removeStation,
  validateBuilder,
} from "../satgonetem_gui/static/scenario_builder_model.js";

function state(overrides = {}) {
  return { ...defaultBuilderState(), ...overrides };
}

describe("scenario builder defaults", () => {
  it("starts with one LEO shell and Berlin", () => {
    const value = defaultBuilderState();

    expect(value.shells).toHaveLength(1);
    expect(value.shells[0].identifier).toBe("LEO");
    expect(value.stations[0].name).toBe("Berlin");
    expect(value.duration_s).toBe(30);
  });

  it("adds uniquely named rows and removes them", () => {
    let value = addShell(state());
    value = addShell(value);
    expect(value.shells.map((shell) => shell.identifier)).toEqual([
      "LEO",
      "LEO2",
      "LEO3",
    ]);

    value = removeShell(value, 1);
    expect(value.shells.map((shell) => shell.identifier)).toEqual([
      "LEO",
      "LEO3",
    ]);

    value = addStation(value);
    expect(value.stations.map((station) => station.name)).toEqual([
      "Berlin",
      "Station 2",
    ]);
    value = removeStation(value, 0);
    expect(value.stations.map((station) => station.name)).toEqual([
      "Station 2",
    ]);
  });
});

describe("scenario builder validation", () => {
  it("accepts the defaults", () => {
    expect(validateBuilder(defaultBuilderState())).toEqual([]);
  });

  it("rejects header and shell errors", () => {
    const errors = validateBuilder(
      state({
        name: " ",
        duration_s: 0,
        tick_s: 0,
        metrics_interval_s: 0,
        shells: [
          { ...defaultBuilderState().shells[0], identifier: "" },
          { ...defaultBuilderState().shells[0], identifier: "" },
        ],
      }),
    );

    expect(errors).toEqual(
      expect.arrayContaining([
        "Name is required.",
        "Duration must be greater than zero.",
        "Tick must be a positive integer.",
        "Metrics interval must be greater than zero.",
        "Shell 1 needs an identifier.",
        "Shell 2 needs an identifier.",
      ]),
    );
  });

  it("rejects duplicate identifiers and bad values", () => {
    const errors = validateBuilder(
      state({
        shells: [
          { ...defaultBuilderState().shells[0] },
          {
            identifier: "LEO",
            planes: 0,
            satellites_per_plane: 0,
            inclination_deg: 181,
            revs_per_day: 0,
            pattern: "bogus",
          },
        ],
        stations: [
          { name: "Berlin", latitude: 91, longitude: -181, elevation_km: -1 },
          { name: "Berlin", latitude: 0, longitude: 0, elevation_km: 0 },
        ],
      }),
    );

    expect(errors).toEqual(
      expect.arrayContaining([
        "Shell identifiers must be unique.",
        "Shell 2 planes must be at least 1.",
        "Shell 2 satellites per plane must be at least 1.",
        "Shell 2 inclination must be between 0 and 180.",
        "Shell 2 revs per day must be greater than zero.",
        "Shell 2 pattern must be star or delta.",
        "Station 1 latitude must be between -90 and 90.",
        "Station 1 longitude must be between -180 and 180.",
        "Station 1 elevation must be zero or greater.",
        "Station names must be unique.",
      ]),
    );
  });

  it("requires at least one shell and station", () => {
    const errors = validateBuilder(state({ shells: [], stations: [] }));

    expect(errors).toEqual(
      expect.arrayContaining([
        "At least one shell is required.",
        "At least one ground station is required.",
      ]),
    );
  });
});

describe("scenario YAML generation", () => {
  it("generates deterministic YAML for the defaults", () => {
    const yaml = buildScenarioYaml(defaultBuilderState());

    expect(yaml).toBe(
      [
        "name: 'Demo Experiment'",
        "duration_s: 30",
        "tick_s: 1",
        "routing: static",
        "metrics_interval_s: 5",
        "connectivity: false",
        "shells:",
        "  - identifier: LEO",
        "    planes: 3",
        "    satellites_per_plane: 4",
        "    inclination_deg: 53",
        "    revs_per_day: 15.5",
        "    pattern: star",
        "ground_stations:",
        "  - name: Berlin",
        "    latitude: 52.52",
        "    longitude: 13.405",
        "    elevation_km: 0.034",
        "",
      ].join("\n"),
    );
  });

  it("quotes unsafe strings and normalizes newlines", () => {
    const yaml = buildScenarioYaml(
      state({
        name: "O'Reilly\nDemo",
        stations: [
          {
            name: "St. John's",
            latitude: 0,
            longitude: 0,
            elevation_km: 0,
          },
        ],
      }),
    );

    expect(yaml).toContain("name: 'O''Reilly Demo'");
    expect(yaml).toContain("name: 'St. John''s'");
  });

  it("emits multiple shells and stations in order", () => {
    let value = addShell(state());
    value = addStation(value);
    value.shells[1].identifier = "MEO";
    const yaml = buildScenarioYaml(value);

    expect(yaml.indexOf("- identifier: LEO")).toBeLessThan(
      yaml.indexOf("- identifier: MEO"),
    );
    expect(yaml).toContain("  - name: Berlin");
    expect(yaml).toContain("  - name: Station 2");
  });
});
