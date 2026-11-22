import { describe, expect, it } from "vitest";

import {
  formatLoss,
  formatRtt,
  lossBucket,
  pairCount,
  resultMap,
  summaryText,
} from "../satgonetem_gui/static/connectivity_model.js";

describe("connectivity matrix model", () => {
  it("counts ordered pairs", () => {
    expect(pairCount(0)).toBe(0);
    expect(pairCount(1)).toBe(0);
    expect(pairCount(2)).toBe(2);
    expect(pairCount(8)).toBe(56);
  });

  it("maps loss to heatmap buckets", () => {
    expect(lossBucket(0, true)).toBe("loss-none");
    expect(lossBucket(10, true)).toBe("loss-low");
    expect(lossBucket(50, true)).toBe("loss-mid");
    expect(lossBucket(90, true)).toBe("loss-high");
    expect(lossBucket(100, true)).toBe("loss-full");
    expect(lossBucket(0, false)).toBe("unreachable");
    expect(lossBucket(null, false)).toBe("unreachable");
  });

  it("formats loss and RTT values", () => {
    expect(formatLoss(0)).toBe("0%");
    expect(formatLoss(12.34)).toBe("12.3%");
    expect(formatLoss(null)).toBe("\u2014");
    expect(formatRtt(1.234)).toBe("1.23 ms");
    expect(formatRtt(null)).toBe("\u2014");
  });

  it("indexes results by source and destination", () => {
    const map = resultMap([
      { source: "A", destination: "B", reachable: true },
      { source: "B", destination: "A", reachable: false },
    ]);

    expect(map.get("A\u0000B").reachable).toBe(true);
    expect(map.get("B\u0000A").reachable).toBe(false);
  });

  it("formats a readable summary", () => {
    expect(
      summaryText({ pairs: 56, reachable: 54, unreachable: 2 }, 12_300),
    ).toBe("56 pairs · 54 reachable · 2 unreachable · 12.3 s");
  });
});
