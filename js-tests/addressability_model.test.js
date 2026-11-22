import { describe, expect, it } from "vitest";

import {
  addressabilityCheckboxState,
  addressabilitySummary,
  routingRefreshMessage,
} from "../satgonetem_gui/static/addressability_model.js";

describe("satellite addressability summary", () => {
  it("distinguishes none, some, and all", () => {
    expect(addressabilitySummary(0, 100)).toBe(
      "No satellites addressable (0 of 100)",
    );
    expect(addressabilitySummary(7, 100)).toBe(
      "7 of 100 satellites addressable",
    );
    expect(addressabilitySummary(100, 100)).toBe(
      "All 100 satellites addressable",
    );
  });

  it("handles missing or empty constellations", () => {
    expect(addressabilitySummary(0, 0)).toBe("No satellites available");
    expect(addressabilitySummary(0, null)).toBe("No satellites available");
  });
});

describe("satellite addressability checkbox", () => {
  it("is unchecked and disabled without a constellation", () => {
    expect(addressabilityCheckboxState(0, 0)).toEqual({
      checked: false,
      indeterminate: false,
      disabled: true,
    });
  });

  it("is indeterminate for a partial selection", () => {
    expect(addressabilityCheckboxState(3, 100)).toEqual({
      checked: true,
      indeterminate: true,
      disabled: false,
    });
  });

  it("is checked when every satellite is addressable", () => {
    expect(addressabilityCheckboxState(100, 100)).toEqual({
      checked: true,
      indeterminate: false,
      disabled: false,
    });
  });
});

describe("routing refresh message", () => {
  it("asks for a re-apply only when routing is active", () => {
    expect(routingRefreshMessage(false)).toBe("Satellite endpoints updated.");
    expect(routingRefreshMessage(true)).toContain("Re-apply Addressing");
  });
});
