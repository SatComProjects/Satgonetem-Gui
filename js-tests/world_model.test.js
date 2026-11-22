import { describe, expect, it } from "vitest";

import {
  describeGroundStation,
  describeSatellite,
  formatCoordinate,
} from "../satgonetem_gui/static/world_model.js";

describe("world entity descriptions", () => {
  it("escapes names and city labels", () => {
    const satellite = describeSatellite("<img src=x>", {});
    const station = describeGroundStation("A&B", "<b>City</b>", {}, true);

    expect(satellite).not.toContain("<img src=x>");
    expect(satellite).toContain("&lt;img src=x&gt;");
    expect(station).toContain("A&amp;B");
    expect(station).toContain("&lt;b&gt;City&lt;/b&gt;");
  });

  it("renders missing coordinates as a dash", () => {
    expect(formatCoordinate(null)).toBe("-");
    expect(formatCoordinate(undefined)).toBe("-");
    expect(formatCoordinate("not-a-number")).toBe("-");
    expect(formatCoordinate(12.345, 1)).toBe("12.3");
  });

  it("renders satellite and station status text", () => {
    expect(
      describeSatellite("Sat0", { latitude: 1, longitude: 2, altitude: 500 }),
    ).toContain("Alt: 500 km");
    expect(describeGroundStation("Gnd0", null, {}, false)).toContain(
      "Status: Disconnected",
    );
  });
});
