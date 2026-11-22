import { describe, expect, it } from "vitest";

import {
  formatElapsed,
  formatEstimate,
  hasBlockingCheck,
  phaseLabel,
  preflightSummary,
  progressPercent,
} from "../satgonetem_gui/static/preflight_model.js";

describe("preflight summary", () => {
  it("distinguishes ready, warnings, and blocking failures", () => {
    expect(
      preflightSummary({
        blocking: false,
        checks: [{ status: "ok" }, { status: "ok" }],
      }),
    ).toBe("All checks passed.");
    expect(
      preflightSummary({
        blocking: false,
        checks: [{ status: "ok" }, { status: "warning" }],
      }),
    ).toBe("Ready with 1 warning.");
    expect(preflightSummary({ blocking: true, checks: [] })).toContain(
      "Blocked",
    );
    expect(preflightSummary(null)).toBe("Checking...");
  });

  it("detects blocking checks", () => {
    expect(hasBlockingCheck([{ status: "warning" }])).toBe(false);
    expect(hasBlockingCheck([{ status: "error" }])).toBe(true);
    expect(hasBlockingCheck(null)).toBe(false);
  });
});

describe("estimate formatting", () => {
  it("formats containers and a rough memory estimate", () => {
    expect(
      formatEstimate({
        satellites: 100,
        ground_stations: 1,
        containers: 101,
        estimated_memory_mb: 12_928,
      }),
    ).toBe(
      "100 satellites · 1 ground station · 101 containers · ~12.6 GB RAM (rough)",
    );
    expect(formatEstimate(null)).toBe("");
  });
});

describe("project phase formatting", () => {
  it("maps phases to readable labels", () => {
    expect(phaseLabel("validating")).toBe("Validating configuration");
    expect(phaseLabel("building")).toBe("Building topology");
    expect(phaseLabel("finalizing")).toBe("Finalizing project");
    expect(phaseLabel("ready")).toBe("Ready");
    expect(phaseLabel(null)).toBe("Working");
    expect(phaseLabel("custom_phase")).toBe("custom phase");
  });

  it("formats elapsed time", () => {
    expect(formatElapsed(500)).toBe("<1 s");
    expect(formatElapsed(12_345)).toBe("12.3 s");
    expect(formatElapsed(62_000)).toBe("1m 02s");
    expect(formatElapsed(null)).toBe("");
  });

  it("normalizes progress and distinguishes indeterminate", () => {
    expect(progressPercent(0)).toBe(0);
    expect(progressPercent(55.4)).toBe(55);
    expect(progressPercent(120)).toBe(100);
    expect(progressPercent(-5)).toBe(0);
    expect(progressPercent(null)).toBeNull();
    expect(progressPercent(undefined)).toBeNull();
  });
});
