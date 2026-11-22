import { describe, expect, it } from "vitest";

import {
  activeCount,
  addItem,
  cloneQueueItem,
  findItem,
  isTerminal,
  normalizeStoredItems,
  pollRetryDelay,
  remainingDelay,
  removeItem,
  replayQueueItem,
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

  it("starts new items with no poll failures or scheduled time", () => {
    const before = Date.now();
    const items = addItem([], fields, "q1");

    expect(items[0].poll_failures).toBe(0);
    expect(items[0].start_at).toBeNull();
    expect(items[0].created_at).toBeGreaterThanOrEqual(before);
    expect(items[0].started_at).toBeNull();
  });

  it("preserves valid run timestamps and defaults old storage safely", () => {
    const items = normalizeStoredItems([
      {
        id: "q1",
        kind: "ping",
        created_at: 1_000,
        started_at: 2_000,
      },
      { id: "q2", kind: "ping", created_at: "bad", started_at: "" },
      { id: "q3", kind: "ping" },
    ]);

    expect(items[0].created_at).toBe(1_000);
    expect(items[0].started_at).toBe(2_000);
    expect(items[1].created_at).toBeNull();
    expect(items[1].started_at).toBeNull();
    expect(items[2].created_at).toBeNull();
    expect(items[2].started_at).toBeNull();
  });

  it("computes remaining delay and restores start_at from storage", () => {
    const items = normalizeStoredItems([
      { id: "q1", kind: "ping", status: "scheduled", start_at: 5_000 },
      { id: "q2", kind: "ping", status: "scheduled", start_at: "bad" },
      { id: "q3", kind: "ping", status: "scheduled", start_at: null },
    ]);

    expect(items[0].start_at).toBe(5_000);
    expect(remainingDelay(items[0], 4_000)).toBe(1_000);
    expect(remainingDelay(items[0], 6_000)).toBe(0);
    expect(items[1].start_at).toBeNull();
    expect(remainingDelay(items[1], 4_000)).toBeNull();
    expect(items[2].start_at).toBeNull();
  });

  it("normalizes persisted items defensively", () => {
    const items = normalizeStoredItems([
      { id: "q1", kind: "ping", payload: {}, status: "done" },
      { id: "q2", kind: "ping", poll_failures: 3 },
      { id: "q3", kind: "ping", poll_failures: "bad" },
      { bad: true },
      null,
    ]);

    expect(items).toHaveLength(3);
    expect(items[0].id).toBe("q1");
    expect(items[0].results).toBeNull();
    expect(items[0].poll_failures).toBe(0);
    expect(items[1].poll_failures).toBe(3);
    expect(items[2].poll_failures).toBe(0);
  });

  it("clones an item without sharing payload or job state", () => {
    const original = {
      id: "q1",
      kind: "hping3",
      payload: { src: "Sat0", dst: "Sat1", flags: ["S"] },
      label: "hping3 tcp Sat0 -> Sat1",
      delay: 4,
      status: "done",
      job_id: "job-1",
      results: { packet_loss_percent: 0 },
    };

    const copy = cloneQueueItem(original);

    expect(copy.id).not.toBe("q1");
    expect(copy.status).toBe("queued");
    expect(copy.job_id).toBeNull();
    expect(copy.results).toBeNull();
    expect(copy.label).toBe("hping3 tcp Sat0 -> Sat1 (copy)");
    expect(copy.payload).toEqual(original.payload);
    expect(copy.payload).not.toBe(original.payload);
    copy.payload.flags.push("A");
    expect(original.payload.flags).toEqual(["S"]);
    expect(cloneQueueItem(copy).label).toBe(
      "hping3 tcp Sat0 -> Sat1 (copy)",
    );
  });

  it("replays a history record as a fresh queued item", () => {
    const replay = replayQueueItem({
      id: "run-1",
      kind: "ping",
      payload: { src: "Gnd0", dst: "Gnd1", count: 5 },
      label: "ping Gnd0 -> Gnd1 (5)",
    });

    expect(replay.status).toBe("queued");
    expect(replay.delay).toBe(0);
    expect(replay.job_id).toBeNull();
    expect(replay.label).toBe("ping Gnd0 -> Gnd1 (5) (replay)");
    expect(replay.payload).toEqual({ src: "Gnd0", dst: "Gnd1", count: 5 });
  });

  it("backs off status polling instead of abandoning the job", () => {
    expect(pollRetryDelay(1)).toBe(1500);
    expect(pollRetryDelay(5)).toBe(2000);
    expect(pollRetryDelay(6)).toBe(4000);
    expect(pollRetryDelay(9)).toBe(30000);
    expect(pollRetryDelay(20)).toBe(30000);
  });
});
