import { describe, expect, it } from "vitest";

import {
  normalizeProjectName,
  validateGroundNumbers,
  validateShellNumbers,
} from "../satgonetem_gui/static/new_project_model.js";

describe("new project form model", () => {
  it("trims names so the backend and polling compare the same value", () => {
    expect(normalizeProjectName("  Demo  ")).toBe("Demo");
    expect(normalizeProjectName("Demo")).toBe("Demo");
  });

  it("rejects invalid orbit-shell numbers", () => {
    expect(validateShellNumbers(10, 10, 70, 14.4)).toBeNull();
    expect(validateShellNumbers(0, 10, 70, 14.4)).toMatch("Planes");
    expect(validateShellNumbers(10, 1.5, 70, 14.4)).toMatch("Satellites");
    expect(validateShellNumbers(10, 10, 181, 14.4)).toMatch("Inclination");
    expect(validateShellNumbers(10, 10, 70, 101)).toMatch("Revolutions");
    expect(validateShellNumbers(1000, 1000, 70, 14.4)).toMatch("10000");
  });

  it("rejects invalid ground-object numbers", () => {
    expect(validateGroundNumbers(10, 3)).toBeNull();
    expect(validateGroundNumbers(-1, 3)).toMatch("Elevation");
    expect(validateGroundNumbers(10, 0)).toMatch("Maximum");
  });

  it("normalizes missing and whitespace-only values to empty", () => {
    expect(normalizeProjectName(null)).toBe("");
    expect(normalizeProjectName(undefined)).toBe("");
    expect(normalizeProjectName("   ")).toBe("");
  });
});
