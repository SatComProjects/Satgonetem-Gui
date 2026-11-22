import { describe, expect, it } from "vitest";

import {
  formatSimRate,
  formatSimTime,
  formatSimulationError,
  normalizeSeekStep,
  progressPercent,
  simulationActionState,
} from "../satgonetem_gui/static/simulation_model.js";

describe("simulation progress", () => {
  it("clamps the step percentage", () => {
    expect(progressPercent(0, 120)).toBe(0);
    expect(progressPercent(60, 120)).toBe(50);
    expect(progressPercent(120, 120)).toBe(100);
    expect(progressPercent(999, 120)).toBe(100);
    expect(progressPercent(-5, 120)).toBe(0);
  });

  it("returns zero when there is no duration", () => {
    expect(progressPercent(3, null)).toBe(0);
    expect(progressPercent(3, 0)).toBe(0);
    expect(progressPercent(null, 120)).toBe(0);
  });
});

describe("simulation formatting", () => {
  it("formats playback rate", () => {
    expect(formatSimRate(1)).toBe("1\u00d7");
    expect(formatSimRate(0.67)).toBe("0.67\u00d7");
    expect(formatSimRate(0)).toBe("-");
    expect(formatSimRate(null)).toBe("-");
  });

  it("formats ISO timestamps without hiding UTC", () => {
    expect(formatSimTime("2024-01-01T00:00:00")).toBe("2024-01-01 00:00:00");
    expect(formatSimTime("2024-01-01T00:00:00.123Z")).toBe(
      "2024-01-01 00:00:00 UTC",
    );
    expect(formatSimTime(null)).toBe("-");
  });

  it("formats the last tick error", () => {
    expect(formatSimulationError(null)).toBe("");
    expect(formatSimulationError("ValueError: boom")).toBe(
      "Last tick failed: ValueError: boom",
    );
  });
});

describe("simulation action state", () => {
  it("disables transport before a project is loaded", () => {
    const state = simulationActionState({
      constellation_loaded: false,
      simulation_updating: false,
    });

    expect(state.startDisabled).toBe(true);
    expect(state.stepDisabled).toBe(true);
    expect(state.resetDisabled).toBe(true);
    expect(state.seekDisabled).toBe(true);
    expect(state.speedDisabled).toBe(true);
  });

  it("allows stepping while paused", () => {
    const state = simulationActionState({
      constellation_loaded: true,
      simulation_updating: false,
    });

    expect(state.startLabel).toBe("Start");
    expect(state.startDisabled).toBe(false);
    expect(state.stepDisabled).toBe(false);
    expect(state.seekDisabled).toBe(false);
  });

  it("requires pause before stepping, resetting, or seeking", () => {
    const state = simulationActionState({
      constellation_loaded: true,
      simulation_updating: true,
    });

    expect(state.startLabel).toBe("Pause");
    expect(state.startDisabled).toBe(false);
    expect(state.stepDisabled).toBe(true);
    expect(state.resetDisabled).toBe(true);
    expect(state.seekDisabled).toBe(true);
    expect(state.speedDisabled).toBe(false);
  });
});

describe("seek input validation", () => {
  it("accepts whole steps inside the project duration", () => {
    expect(normalizeSeekStep("0", 120)).toBe(0);
    expect(normalizeSeekStep("42", 120)).toBe(42);
    expect(normalizeSeekStep(120, 120)).toBe(120);
  });

  it("rejects blanks, fractions, and out-of-range values", () => {
    expect(normalizeSeekStep("", 120)).toBeNull();
    expect(normalizeSeekStep("   ", 120)).toBeNull();
    expect(normalizeSeekStep(null, 120)).toBeNull();
    expect(normalizeSeekStep("1.5", 120)).toBeNull();
    expect(normalizeSeekStep("-1", 120)).toBeNull();
    expect(normalizeSeekStep("121", 120)).toBeNull();
    expect(normalizeSeekStep("4", null)).toBeNull();
  });
});
