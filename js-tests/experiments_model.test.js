import { describe, expect, it } from "vitest";

import {
  DEFAULT_SCENARIO,
  artifactLabel,
  experimentModeLabel,
  experimentStatusLabel,
  experimentSummaryText,
  formatExperimentDate,
} from "../satgonetem_gui/static/experiments_model.js";

describe("experiment run formatting", () => {
  it("labels status and modes", () => {
    expect(experimentStatusLabel("running")).toBe("Running");
    expect(experimentStatusLabel("done")).toBe("Done");
    expect(experimentStatusLabel("error")).toBe("Failed");
    expect(experimentModeLabel("dry_run")).toBe("Validate only");
    expect(experimentModeLabel("offline")).toBe("Offline");
    expect(experimentModeLabel("live")).toBe("Live");
  });

  it("formats timestamps and artifact names", () => {
    expect(formatExperimentDate("2026-01-02T03:04:05.123Z")).toBe(
      "2026-01-02 03:04:05 UTC",
    );
    expect(formatExperimentDate(null)).toBe("\u2014");
    expect(artifactLabel("metrics.jsonl")).toBe("Metrics");
    expect(artifactLabel("unknown.bin")).toBe("unknown.bin");
  });

  it("summarizes flows and connectivity", () => {
    expect(
      experimentSummaryText({
        flows: { count: 3, errors: 1 },
        connectivity: { reachable: 4, pairs: 6 },
      }),
    ).toBe("3 flows (1 errors) \u00b7 4/6 reachable");
    expect(experimentSummaryText({ errors: ["bad"] })).toBe("1 error");
    expect(experimentSummaryText(null)).toBe("\u2014");
  });

  it("ships a valid-looking walker sample scenario", () => {
    expect(DEFAULT_SCENARIO).toContain("duration_s: 30");
    expect(DEFAULT_SCENARIO).toContain("planes: 3");
    expect(DEFAULT_SCENARIO).toContain("name: Berlin");
  });
});
