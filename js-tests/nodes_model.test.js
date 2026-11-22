import { describe, expect, it } from "vitest";

import {
  DETAIL_TTL_MS,
  cacheEntry,
  isFresh,
  staleCacheKeys,
} from "../satgonetem_gui/static/nodes_model.js";

describe("node detail cache", () => {
  it("treats entries inside the TTL as fresh", () => {
    const entry = cacheEntry({ name: "Sat0" }, 1_000);

    expect(isFresh(entry, 1_000 + DETAIL_TTL_MS - 1)).toBe(true);
  });

  it("expires entries at and beyond the TTL", () => {
    const entry = cacheEntry({ name: "Sat0" }, 1_000);

    expect(isFresh(entry, 1_000 + DETAIL_TTL_MS)).toBe(false);
    expect(isFresh(entry, 1_000 + DETAIL_TTL_MS + 1)).toBe(false);
  });

  it("handles missing entries", () => {
    expect(isFresh(null)).toBe(false);
    expect(isFresh(undefined)).toBe(false);
  });

  it("identifies cache entries for nodes that disappeared", () => {
    expect(
      staleCacheKeys(["Sat0", "Sat1", "Station"], ["Sat1", "Station", "Sat2"]),
    ).toEqual(["Sat0"]);
    expect(staleCacheKeys(["Sat0"], ["Sat0"])).toEqual([]);
  });
});
