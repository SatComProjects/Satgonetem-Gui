import { describe, expect, it } from "vitest";

import {
  formatThroughput,
  heatLevel,
  matrixMax,
  matrixSummary,
  statusLabel,
} from "../satgonetem_gui/static/traffic_matrix_model.js";

describe("traffic matrix formatting", () => {
  it("formats throughput and summaries", () => {
    expect(formatThroughput(10.234)).toBe("10.2 Mbps");
    expect(formatThroughput(0)).toBe("0.0 Mbps");
    expect(formatThroughput(null)).toBe("\u2014");
    expect(statusLabel("running")).toBe("Running");
    expect(statusLabel("done")).toBe("Done");
    expect(statusLabel("error")).toBe("Failed");
    expect(
      matrixSummary({
        status: "running",
        pairs_completed: 2,
        pairs_total: 6,
      }),
    ).toBe("Running \u00b7 2/6 pairs");
    expect(matrixSummary(null)).toBe("\u2014");
  });

  it("computes the matrix max and heat levels", () => {
    expect(matrixMax([[null, 10], [20, null]])).toBe(20);
    expect(matrixMax([])).toBe(0);
    expect(heatLevel(20, 20)).toBe(4);
    expect(heatLevel(15, 20)).toBe(4);
    expect(heatLevel(10, 20)).toBe(3);
    expect(heatLevel(5, 20)).toBe(2);
    expect(heatLevel(1, 20)).toBe(1);
    expect(heatLevel(null, 20)).toBe(0);
    expect(heatLevel(5, 0)).toBe(0);
  });
});
