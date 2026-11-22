import { describe, expect, it } from "vitest";

import { normalizeProjectName } from "../satgonetem_gui/static/new_project_model.js";

describe("new project form model", () => {
  it("trims names so the backend and polling compare the same value", () => {
    expect(normalizeProjectName("  Demo  ")).toBe("Demo");
    expect(normalizeProjectName("Demo")).toBe("Demo");
  });

  it("normalizes missing and whitespace-only values to empty", () => {
    expect(normalizeProjectName(null)).toBe("");
    expect(normalizeProjectName(undefined)).toBe("");
    expect(normalizeProjectName("   ")).toBe("");
  });
});
