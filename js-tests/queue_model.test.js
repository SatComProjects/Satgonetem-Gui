import { describe, expect, it } from "vitest";

import {
  activeCount,
  addItem,
  findItem,
  isTerminal,
  normalizeStoredItems,
  removeItem,
  startableItems,
  updateItem,
} from "../satgonetem_gui/static/queue_model.js";

const fields = {
  kind: "ping",
  payload: { src: "Sat0", dst: "Sat1" },
  label: "ping Sat0 -> Sat1",
};

describe("queue model", () => {
  it("uses stable IDs instead of indexes", () => {
    let items = addItem([], fields, "q1");
    items = addItem(items, { ...fields, label: "second" }, "q2");
    items = removeItem(items, "q1");

    expect(items).toHaveLength(1);
    expect(findItem(items, "q2").label).toBe("second");
    expect(findItem(items, "q1")).toBeNull();
  });

  it("updates one item without touching the others", () => {
    let items = addItem([], fields, "q1");
    items = addItem(items, fields, "q2");

    items = updateItem(items, "q1", { status: "running", job_id: "j1" });

    expect(findItem(items, "q1").status).toBe("running");
    expect(findItem(items, "q2").status).toBe("queued");
  });

  it("counts only active items and selects startable ones", () => {
    let items = addItem([], fields, "q1");
    items = addItem(items, fields, "q2");
    items = addItem(items, fields, "q3");
    items = updateItem(items, "q1", { status: "running" });
    items = updateItem(items, "q2", { status: "done" });

    expect(activeCount(items)).toBe(2);
    expect(startableItems(items).map((item) => item.id)).toEqual(["q3"]);
    expect(isTerminal(findItem(items, "q2"))).toBe(true);
    expect(isTerminal(findItem(items, "q1"))).toBe(false);
  });

  it("normalizes persisted items defensively", () => {
    const items = normalizeStoredItems([
      { id: "q1", kind: "ping", payload: {}, status: "done" },
      { bad: true },
      null,
    ]);

    expect(items).toHaveLength(1);
    expect(items[0].id).toBe("q1");
    expect(items[0].results).toBeNull();
  });
});
