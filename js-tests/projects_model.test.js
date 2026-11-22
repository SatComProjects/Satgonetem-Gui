import { describe, expect, it } from "vitest";

import {
  formatProjectCount,
  formatProjectDate,
  formatProjectSize,
  projectNameValid,
} from "../satgonetem_gui/static/projects_model.js";

describe("project workspace formatting", () => {
  it("formats file sizes", () => {
    expect(formatProjectSize(512)).toBe("512 B");
    expect(formatProjectSize(2048)).toBe("2 KB");
    expect(formatProjectSize(1_500_000)).toBe("1.43 MB");
    expect(formatProjectSize(2 * 1024 ** 3)).toBe("2 GB");
    expect(formatProjectSize(null)).toBe("\u2014");
  });

  it("formats UTC timestamps deterministically", () => {
    expect(formatProjectDate("2026-01-02T03:04:05.123456Z")).toBe(
      "2026-01-02 03:04:05 UTC",
    );
    expect(formatProjectDate(null)).toBe("\u2014");
  });

  it("formats missing counts without pretending they are zero", () => {
    expect(formatProjectCount(0)).toBe("0");
    expect(formatProjectCount(12)).toBe("12");
    expect(formatProjectCount(null)).toBe("\u2014");
    expect(formatProjectCount(undefined)).toBe("\u2014");
  });

});
