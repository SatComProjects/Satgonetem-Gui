/** Pure queue state helpers shared by the UI and tests. */

export const TERMINAL_STATUSES = new Set(["done", "error", "cancelled"]);
export const ACTIVE_STATUSES = new Set(["queued", "scheduled", "running", "starting"]);

let idCounter = 0;

export function newQueueItem(fields, id = null) {
  idCounter += 1;
  return {
    id: id || `q${Date.now().toString(36)}-${idCounter}`,
    kind: fields.kind || "iperf3",
    payload: fields.payload || {},
    label: fields.label || fields.kind || "job",
    delay: Number(fields.delay) || 0,
    status: "queued",
    job_id: null,
    results: null,
    error: null,
  };
}

export function addItem(items, fields, id = null) {
  return [...items, newQueueItem(fields, id)];
}

export function findItem(items, id) {
  return items.find((item) => item.id === id) || null;
}

export function updateItem(items, id, changes) {
  return items.map((item) => (item.id === id ? { ...item, ...changes } : item));
}

export function removeItem(items, id) {
  return items.filter((item) => item.id !== id);
}

export function activeCount(items) {
  return items.filter((item) => ACTIVE_STATUSES.has(item.status)).length;
}

export function isTerminal(item) {
  return Boolean(item && TERMINAL_STATUSES.has(item.status));
}

export function startableItems(items) {
  return items.filter(
    (item) => item.status === "queued" || item.status === "scheduled",
  );
}

export function normalizeStoredItems(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((item) => item && typeof item === "object" && item.id && item.kind)
    .map((item) => ({
      id: item.id,
      kind: item.kind,
      payload: item.payload || {},
      label: item.label || item.kind,
      delay: Number(item.delay) || 0,
      status: item.status || "queued",
      job_id: item.job_id || null,
      results: item.results || null,
      error: item.error || null,
    }));
}
