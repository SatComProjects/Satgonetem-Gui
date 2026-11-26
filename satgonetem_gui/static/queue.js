/**
 * Shared traffic job queue.
 *
 * This controller owns queue items, stable IDs, timers, cross-tab sync,
 * start/cancel/remove/clear actions, polling with retry/backoff, and the queue
 * panel rendering. Result plots, the results/history dialog, and the history
 * ledger live in their own modules and are wired in from here.
 */
import { api, ApiError } from "./api.js?v=4";
import { byId } from "./dom.js";
import { escapeHtml } from "./escape.js";
import { captureHistory, initHistoryPanel } from "./history_panel.js?v=1";
import {
  addItem,
  activeCount,
  cloneQueueItem,
  findItem,
  isTerminal,
  normalizeStoredItems,
  pollRetryDelay,
  remainingDelay,
  removeItem,
  startableItems,
  updateItem,
} from "./queue_model.js?v=4";
import { initResultsModal } from "./results_modal.js?v=1";
import { destroyCharts, plotResult } from "./traffic_plots.js?v=1";

const JQ_KEY = "sgnt_traffic_queue";
const MAX_POLL_FAILURES = 5;

const jq = { items: [], timers: {} };
let storageSync = false;
const TAB_ID = `${Date.now()}-${Math.random().toString(36).slice(2)}`;

function jqSave() {
  if (storageSync) return;
  const message = byId("jq-storage-msg");
  try {
    const items = jq.items.map(({ results: _results, ...rest }) => rest);
    localStorage.setItem(JQ_KEY, JSON.stringify(items));
    if (message) message.textContent = "";
  } catch {
    if (message) {
      message.textContent =
        "Queue state could not be saved in this browser; active jobs stay tracked in this tab.";
    }
  }
}

function clearTimer(id) {
  if (jq.timers[id]) {
    clearTimeout(jq.timers[id]);
    delete jq.timers[id];
  }
}

function schedule(id, delay, callback) {
  clearTimer(id);
  jq.timers[id] = setTimeout(callback, delay);
}

function cancelJob(jobId) {
  // Best effort: the queue item is already gone, so there is nowhere to show
  // a failure. The server reaps finished jobs on its own.
  api.post("/api/traffic/cancel", { job_id: jobId }).catch(() => {});
}

function claimStart(id) {
  const key = `sgnt_traffic_start_${id}`;
  const now = Date.now();
  try {
    const raw = localStorage.getItem(key);
    if (raw) {
      const claim = JSON.parse(raw);
      if (claim.owner !== TAB_ID && Number(claim.until) > now) {
        return false;
      }
    }
    localStorage.setItem(
      key,
      JSON.stringify({ owner: TAB_ID, until: now + 15_000 }),
    );
    return true;
  } catch {
    return true;
  }
}

function queueInit() {
  jqLoad();
  initHistoryPanel({ addItem: jqAdd });
  jqRender();
  bindStaticControls();
  initResultsModal({
    destroyCharts,
    fallbackFocus: () => byId("jq-toggle")?.focus(),
  });
  window.addEventListener("storage", handleQueueStorage);
}

function bindStaticControls() {
  byId("jq-toggle")?.addEventListener("click", jqToggleCollapsed);
  byId("jq-start-all")?.addEventListener("click", jqStartAll);
  byId("jq-clear")?.addEventListener("click", jqClear);
}

function handleQueueStorage(event) {
  if (event.key !== JQ_KEY) return;
  storageSync = true;
  for (const id of Object.keys(jq.timers)) clearTimer(id);
  jqLoad();
  jqRender();
  storageSync = false;
}

function jqLoad() {
  let stored = [];
  try {
    stored = normalizeStoredItems(JSON.parse(localStorage.getItem(JQ_KEY) || "[]"));
  } catch {
    stored = [];
  }
  jq.items = stored.map((item) => {
    if (item.status === "starting") {
      return { ...item, status: "queued", start_at: null };
    }
    if (item.status === "scheduled" && !Number.isFinite(item.start_at)) {
      return { ...item, status: "queued", start_at: null };
    }
    return item;
  });
  for (const item of jq.items) {
    if (item.status === "running" && item.job_id) {
      schedule(item.id, 0, () => jqTrack(item.id));
    } else if (item.status === "scheduled") {
      const delay = remainingDelay(item);
      schedule(item.id, delay ?? 0, () => jqStartNow(item.id));
    }
  }
  jqSave();
}

function jqToggleCollapsed() {
  const panel = byId("floating-queue");
  if (!panel) return;
  panel.classList.toggle("collapsed");
  const collapsed = panel.classList.contains("collapsed");
  const header = byId("jq-toggle");
  if (header) header.setAttribute("aria-expanded", String(!collapsed));
  const icon = byId("jq-toggle-icon");
  if (icon) {
    icon.textContent = collapsed ? "\u25B2" : "\u25BC";
  }
}

function jqExpand() {
  const panel = byId("floating-queue");
  if (!panel) return;
  panel.classList.remove("collapsed");
  const header = byId("jq-toggle");
  if (header) header.setAttribute("aria-expanded", "true");
  const icon = byId("jq-toggle-icon");
  if (icon) icon.textContent = "\u25BC";
}

function jqUpdateBadge() {
  const badge = byId("jq-badge");
  if (!badge) return;
  const active = activeCount(jq.items);
  badge.textContent = String(active);
  badge.style.display = active > 0 ? "inline-block" : "none";
}

function jqRender() {
  const list = byId("job-queue-list");
  if (!list) return;
  list.replaceChildren();

  if (jq.items.length === 0) {
    const empty = document.createElement("div");
    empty.className = "muted";
    empty.textContent = "No jobs queued.";
    list.appendChild(empty);
    jqUpdateBadge();
    return;
  }

  list.innerHTML = jq.items
    .map((item) => {
      const id = escapeHtml(item.id);
      const canStart = item.status === "queued" || item.status === "scheduled";
      const canRetry = item.status === "error" || item.status === "cancelled";
      const canCancel =
        item.status === "running" || item.status === "scheduled";
      return `
        <div class="queue-item">
          <div class="queue-item-header">
            <span class="queue-kind">${escapeHtml(item.kind)}</span>
            <span class="queue-label">${escapeHtml(item.label)}</span>
            <span class="queue-status">${escapeHtml(item.status)}</span>
          </div>
          ${item.error ? `<div class="queue-error">${escapeHtml(item.error)}</div>` : ""}
          <div class="queue-item-actions">
            ${item.status === "done" ? `<button type="button" class="button small secondary" data-action="plot" data-id="${id}">Plot</button>` : ""}
            ${canStart ? `<button type="button" class="button small" data-action="start" data-id="${id}">Start</button>` : ""}
            ${canRetry ? `<button type="button" class="button small" data-action="start" data-id="${id}">Retry</button>` : ""}
            ${canCancel ? `<button type="button" class="button small secondary" data-action="cancel" data-id="${id}">Cancel</button>` : ""}
            <button type="button" class="button small secondary" data-action="clone" data-id="${id}">Clone</button>
            <button type="button" class="button small secondary" data-action="remove" data-id="${id}">Remove</button>
          </div>
        </div>`;
    })
    .join("");

  list.querySelectorAll("button[data-action]").forEach((button) => {
    button.addEventListener("click", () => {
      const id = button.dataset.id;
      switch (button.dataset.action) {
        case "plot":
          jqPlot(id);
          break;
        case "start":
          jqStartOne(id);
          break;
        case "cancel":
          jqCancel(id);
          break;
        case "clone":
          jqClone(id);
          break;
        case "remove":
          jqRemove(id);
          break;
        default:
          break;
      }
    });
  });
  jqUpdateBadge();
}

function jqAdd(item) {
  jq.items = addItem(jq.items, item);
  const created = jq.items[jq.items.length - 1];
  jqSave();
  jqRender();
  jqExpand();
  return created.id;
}

function jqClone(id) {
  const item = findItem(jq.items, id);
  if (!item) return;
  jqAdd(cloneQueueItem(item));
}

function jqRemove(id) {
  const item = findItem(jq.items, id);
  if (item && item.status === "running" && item.job_id) {
    cancelJob(item.job_id);
  }
  clearTimer(id);
  jq.items = removeItem(jq.items, id);
  jqSave();
  jqRender();
}

function jqClear() {
  for (const item of jq.items) {
    if (item.status === "running" && item.job_id) {
      cancelJob(item.job_id);
    }
  }
  for (const id of Object.keys(jq.timers)) clearTimer(id);
  jq.items = [];
  jqSave();
  jqRender();
}

function jqStartAll() {
  for (const item of startableItems(jq.items)) {
    jqStartOne(item.id);
  }
}

function jqStartOne(id) {
  const item = findItem(jq.items, id);
  if (!item || item.status === "running" || item.status === "starting") return;
  if (item.status === "scheduled") {
    clearTimer(id);
    jq.items = updateItem(jq.items, id, {
      status: "starting",
      start_at: null,
      error: null,
    });
    jqSave();
    jqRender();
    schedule(id, 0, () => jqStartNow(id));
    return;
  }
  const delayMs = Math.max(0, (Number(item.delay) || 0) * 1000);
  jq.items = updateItem(jq.items, id, {
    status: delayMs > 0 ? "scheduled" : "starting",
    start_at: delayMs > 0 ? Date.now() + delayMs : null,
    error: null,
  });
  jqSave();
  jqRender();
  schedule(id, delayMs, () => jqStartNow(id));
}

async function jqStartNow(id) {
  clearTimer(id);
  const item = findItem(jq.items, id);
  if (!item) return false;
  if (!claimStart(id)) return false;
  jq.items = updateItem(jq.items, id, {
    status: "starting",
    start_at: null,
    error: null,
  });
  jqSave();
  jqRender();
  let data;
  try {
    data = await api.post(`/api/traffic/${item.kind}`, item.payload);
  } catch (error) {
    const current = findItem(jq.items, id);
    if (current && !isTerminal(current)) {
      jq.items = updateItem(jq.items, id, {
        status: "error",
        error: error.message || "Start failed",
      });
      jqSave();
      jqRender();
    }
    return false;
  }
  const current = findItem(jq.items, id);
  if (!current || isTerminal(current)) {
    // The item was removed, cleared, or cancelled while the start request was
    // in flight, so cancel the orphaned backend job instead of resurrecting it.
    cancelJob(data.job_id);
    return false;
  }
  jq.items = updateItem(jq.items, id, {
    status: "running",
    job_id: data.job_id,
    started_at: Date.now(),
    poll_failures: 0,
    error: null,
  });
  jqSave();
  jqRender();
  jqTrack(id);
  return true;
}

async function jqTrack(id) {
  clearTimer(id);
  const item = findItem(jq.items, id);
  if (!item || !item.job_id || isTerminal(item)) return;

  try {
    const status = await api.get(
      `/api/traffic/status?job_id=${encodeURIComponent(item.job_id)}`,
    );
    const current = findItem(jq.items, id);
    if (!current || isTerminal(current)) return;
    if (status.status === "done") {
      jq.items = updateItem(jq.items, id, {
        status: "done",
        results: status.results || null,
        poll_failures: 0,
      });
      jqSave();
      jqRender();
      captureHistory(current, status.results || null);
      return;
    }
    if (status.status === "error") {
      jq.items = updateItem(jq.items, id, {
        status: "error",
        error: status.error || "Unknown error",
        poll_failures: 0,
      });
      jqSave();
      jqRender();
      return;
    }
    if (status.status === "cancelled") {
      jq.items = updateItem(jq.items, id, {
        status: "cancelled",
        poll_failures: 0,
      });
      jqSave();
      jqRender();
      return;
    }
    if (status.status !== "running") {
      jq.items = updateItem(jq.items, id, {
        status: "error",
        error: `Unknown job status: ${status.status ?? "missing"}`,
        poll_failures: 0,
      });
      jqSave();
      jqRender();
      return;
    }
    if (current.poll_failures || current.error) {
      jq.items = updateItem(jq.items, id, {
        poll_failures: 0,
        error: null,
      });
      jqSave();
      jqRender();
    }
    schedule(id, 1000, () => jqTrack(id));
  } catch (error) {
    const current = findItem(jq.items, id);
    if (!current || isTerminal(current)) return;
    if (error instanceof ApiError && error.status === 404) {
      jq.items = updateItem(jq.items, id, {
        status: "error",
        error: error.message || "Job not found",
      });
      jqSave();
      jqRender();
      return;
    }
    const failures = (current.poll_failures || 0) + 1;
    jq.items = updateItem(jq.items, id, {
      poll_failures: failures,
      error:
        failures >= MAX_POLL_FAILURES
          ? `Status check failed ${failures} times; retrying: ${error.message || "network error"}`
          : current.error,
    });
    jqSave();
    jqRender();
    schedule(id, pollRetryDelay(failures), () => jqTrack(id));
  }
}

async function jqCancel(id) {
  const item = findItem(jq.items, id);
  if (!item || isTerminal(item)) return;
  clearTimer(id);
  if (item.job_id) {
    try {
      await api.post("/api/traffic/cancel", { job_id: item.job_id });
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        // The job finished before the cancel arrived; refresh to pick up its
        // terminal result instead of replacing it with an error.
        jqTrack(id);
        return;
      }
      const current = findItem(jq.items, id);
      if (current && !isTerminal(current)) {
        jq.items = updateItem(jq.items, id, {
          error: error.message || "Cancel failed",
        });
        jqSave();
        jqRender();
        if (current.job_id) {
          schedule(id, 1500, () => jqTrack(id));
        }
      }
      return;
    }
  }
  const current = findItem(jq.items, id);
  if (!current || isTerminal(current)) return;
  jq.items = updateItem(jq.items, id, { status: "cancelled" });
  jqSave();
  jqRender();
}

async function jqPlot(id) {
  let item = findItem(jq.items, id);
  if (!item) return;

  if (!item.results && item.job_id) {
    try {
      const status = await api.get(
        `/api/traffic/status?job_id=${encodeURIComponent(item.job_id)}`,
      );
      if (status.status === "done" && status.results) {
        jq.items = updateItem(jq.items, id, {
          status: "done",
          results: status.results,
          poll_failures: 0,
        });
        jqSave();
        jqRender();
        item = findItem(jq.items, id);
        captureHistory(item, status.results);
      }
    } catch (error) {
      jq.items = updateItem(jq.items, id, {
        error: error.message || "Could not load results",
      });
      jqSave();
      jqRender();
      return;
    }
  }

  if (!item || !item.results) {
    if (item) {
      jq.items = updateItem(jq.items, id, {
        error: "Results are not available for this job.",
      });
      jqSave();
      jqRender();
    }
    return;
  }
  plotResult(item.kind, item);
}

queueInit();

export { jqAdd, jqStartNow, jqStartOne };
