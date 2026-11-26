/**
 * Dashboard status polling and routing controls.
 *
 * Polls /api/status every 2 seconds for constellation / emulation state and
 * /api/routing/status for routing state. Allows the user to start/stop
 * GoNetem and to apply or delete addressing and routing.
 */
import { api } from "./api.js?v=4";
import { setStatus } from "./dom.js";
import { initSimulationControls } from "./simulation_controls.js?v=2";
import { runPreflight } from "./preflight_ui.js?v=2";

const POLL_INTERVAL_MS = 2000;
const simulation = initSimulationControls({ poll: false });

/**
 * @param {string} id - Element id.
 * @returns {HTMLElement}
 */
function el(id) {
  return document.getElementById(id);
}

/**
 * Set a status dot to ok (green) or bad (red).
 *
 * @param {HTMLElement} dot
 * @param {boolean} ok
 */
function setDot(dot, ok) {
  dot.classList.toggle("ok", ok);
  dot.classList.toggle("bad", !ok);
}

/** @type {{ constellation_loaded: boolean, gonetem_is_on: boolean } | null} */
let lastStatus = null;

/** @type {boolean} */
let gonetemBusy = false;
let statusInFlight = false;
let routingInFlight = false;
let routingBusy = false;
let preflightInFlight = false;

/**
 * Apply a status snapshot from /api/status to the DOM.
 *
 * @param {Object} data - Status object from the API.
 * @param {boolean} data.constellation_loaded
 * @param {number} data.satellites
 * @param {number} data.ground_stations
 * @param {number} data.links
 * @param {boolean} data.gonetem_is_on
 * @param {boolean} data.simulation_updating
 * @param {number|null} data.current_step
 * @param {string|null} data.current_time
 */
function applyStatus(data) {
  lastStatus = data;

  setDot(el("dot-loaded"), data.constellation_loaded);
  el("label-loaded").textContent = data.constellation_loaded ? "Loaded" : "Not loaded";

  el("val-satellites").textContent = data.constellation_loaded ? data.satellites : "-";
  el("val-ground-stations").textContent = data.constellation_loaded ? data.ground_stations : "-";
  el("val-links").textContent = data.constellation_loaded ? data.links : "-";

  setDot(el("dot-gonetem"), data.gonetem_is_on);
  el("label-gonetem").textContent = data.gonetem_is_on ? "Running" : "Stopped";

  if (!gonetemBusy) {
    el("btn-gonetem").textContent = data.gonetem_is_on ? "Stop" : "Start";
  }

  simulation.apply(data);
}

/**
 * Update the routing status card from the latest API data.
 *
 * @param {Object} data
 * @param {boolean} data.gonetem_is_on
 * @param {boolean} data.addressing_applied
 * @param {boolean} data.routing_initiated
 * @param {string|null} data.routing_method
 */
function applyRoutingStatus(data) {
  setDot(el("dot-routing-gonetem"), data.gonetem_is_on);
  el("label-routing-gonetem").textContent = data.gonetem_is_on ? "Running" : "Stopped";

  setDot(el("dot-addressing"), data.addressing_applied);
  el("label-addressing").textContent = data.addressing_applied ? "Applied" : "Not applied";

  setDot(el("dot-routing"), data.routing_initiated);
  el("label-routing").textContent = data.routing_initiated ? "Applied" : "Not applied";

  el("val-method").textContent = data.routing_method || "-";
}

/**
 * Show a transient message under the routing controls.
 *
 * @param {string} text
 * @param {boolean} [isError]
 */
function showRoutingMsg(text, isError) {
  setStatus(el("routing-msg"), text, isError);
}

function showDashboardMsg(text, isError) {
  setStatus(el("dashboard-msg"), text, isError);
}

async function pollStatus() {
  if (statusInFlight) return;
  statusInFlight = true;
  try {
    applyStatus(await api.get("/api/status"));
    showDashboardMsg("");
  } catch (err) {
    showDashboardMsg(
      "Status refresh failed: " + (err.message || "network error"),
      true,
    );
  } finally {
    statusInFlight = false;
  }
}

let routingRefreshFailed = false;

async function pollRoutingStatus() {
  if (routingInFlight) return;
  routingInFlight = true;
  try {
    const data = await api.get("/api/routing/status");
    if (data.ok) applyRoutingStatus(data);
    if (routingRefreshFailed) {
      routingRefreshFailed = false;
      showRoutingMsg("");
    }
  } catch (err) {
    routingRefreshFailed = true;
    showRoutingMsg(
      "Routing status refresh failed: " + (err.message || "network error"),
      true,
    );
  } finally {
    routingInFlight = false;
  }
}

el("btn-gonetem").addEventListener("click", async function () {
  if (!lastStatus || !lastStatus.constellation_loaded) {
    alert("No project is loaded. Load or create a project first.");
    return;
  }
  if (gonetemBusy) return;

  var btn = el("btn-gonetem");
  var starting = !lastStatus.gonetem_is_on;
  var endpoint = starting ? "/api/gonetem/start" : "/api/gonetem/stop";
  gonetemBusy = true;
  btn.textContent = starting ? "Starting..." : "Stopping...";
  try {
    await api.post(endpoint, undefined, { timeout: 600000 });
  } catch (err) {
    alert((starting ? "Start" : "Stop") + " failed: " + (err.message || "Unknown error"));
  } finally {
    gonetemBusy = false;
    btn.textContent = lastStatus?.gonetem_is_on ? "Stop" : "Start";
    await pollStatus();
  }
});

function setRoutingBusy(busy) {
  routingBusy = busy;
  el("btn-apply").disabled = busy;
  el("btn-delete").disabled = busy;
  el("routing-method").disabled = busy;
}

el("btn-apply").addEventListener("click", async function () {
  if (routingBusy) return;
  setRoutingBusy(true);
  var method = el("routing-method").value;
  showRoutingMsg("Applying addressing and routing...");
  try {
    await api.post("/api/routing/apply", { method }, { timeout: 600000 });
    showRoutingMsg("Addressing and routing applied successfully.");
  } catch (err) {
    showRoutingMsg(err.message || "Apply failed.", true);
  } finally {
    setRoutingBusy(false);
  }
  await pollRoutingStatus();
});

el("btn-delete").addEventListener("click", async function () {
  if (routingBusy) return;
  if (!confirm("Delete all installed routes?")) {
    return;
  }
  setRoutingBusy(true);
  showRoutingMsg("Deleting routing...");
  try {
    await api.post("/api/routing/delete", undefined, { timeout: 600000 });
    showRoutingMsg("Routing deleted successfully.");
  } catch (err) {
    showRoutingMsg(err.message || "Delete failed.", true);
  } finally {
    setRoutingBusy(false);
  }
  await pollRoutingStatus();
});

async function refreshPreflight() {
  const checks = el("preflight-checks");
  if (!checks || preflightInFlight) return;
  preflightInFlight = true;
  const button = el("preflight-recheck");
  if (button) button.disabled = true;
  try {
    await runPreflight({
      checksElement: checks,
      msgElement: el("preflight-msg"),
    });
  } catch (err) {
    setStatus(
      el("preflight-msg"),
      "Readiness check failed: " + (err.message || "network error"),
      true,
    );
  } finally {
    preflightInFlight = false;
    if (button) button.disabled = false;
  }
}

el("preflight-recheck")?.addEventListener("click", refreshPreflight);

pollStatus();
setInterval(pollStatus, POLL_INTERVAL_MS);

pollRoutingStatus();
setInterval(pollRoutingStatus, POLL_INTERVAL_MS);
refreshPreflight();
