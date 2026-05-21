/**
 * Dashboard status polling and routing controls.
 *
 * Polls /api/status every 2 seconds for constellation / emulation state and
 * /api/routing/status for routing state. Allows the user to start/stop
 * GoNetem and to apply or delete addressing and routing.
 */

const POLL_INTERVAL_MS = 2000;

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

  setDot(el("dot-running"), data.simulation_updating);
  el("label-running").textContent = data.simulation_updating ? "Updating" : "Idle";

  el("val-step").textContent = data.current_step !== null ? data.current_step : "-";
  el("val-time").textContent = data.current_time !== null ? data.current_time : "-";
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
  var msg = el("routing-msg");
  msg.textContent = text;
  msg.style.color = isError ? "var(--bad)" : "var(--muted)";
}

async function pollStatus() {
  try {
    const response = await fetch("/api/status");
    if (!response.ok) return;
    const data = await response.json();
    applyStatus(data);
  } catch (_) {
    // Network error - keep last known state visible.
  }
}

async function pollRoutingStatus() {
  try {
    var r = await fetch("/api/routing/status");
    if (!r.ok) return;
    var data = await r.json();
    if (data.ok) {
      applyRoutingStatus(data);
    }
  } catch (_) {
    // Ignore network errors.
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
    var r = await fetch(endpoint, { method: "POST" });
    var j = await r.json().catch(function () { return {}; });
    if (!r.ok || !j.ok) {
      alert((starting ? "Start" : "Stop") + " failed: " + (j.error || "Unknown error"));
    }
  } catch (err) {
    alert("Error: " + String(err.message || err));
  } finally {
    gonetemBusy = false;
    await pollStatus();
  }
});

el("btn-apply").addEventListener("click", async function () {
  var method = el("routing-method").value;
  showRoutingMsg("Applying addressing and routing...");
  try {
    var r = await fetch("/api/routing/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ method: method }),
    });
    var j = await r.json().catch(function () { return {}; });
    if (!r.ok || !j.ok) {
      showRoutingMsg(j.error || "Apply failed.", true);
    } else {
      showRoutingMsg("Addressing and routing applied successfully.");
    }
  } catch (err) {
    showRoutingMsg("Error: " + String(err.message || err), true);
  }
  await pollRoutingStatus();
});

el("btn-delete").addEventListener("click", async function () {
  if (!confirm("Delete all installed routes?")) {
    return;
  }
  showRoutingMsg("Deleting routing...");
  try {
    var r = await fetch("/api/routing/delete", { method: "POST" });
    var j = await r.json().catch(function () { return {}; });
    if (!r.ok || !j.ok) {
      showRoutingMsg(j.error || "Delete failed.", true);
    } else {
      showRoutingMsg("Routing deleted successfully.");
    }
  } catch (err) {
    showRoutingMsg("Error: " + String(err.message || err), true);
  }
  await pollRoutingStatus();
});

pollStatus();
setInterval(pollStatus, POLL_INTERVAL_MS);

pollRoutingStatus();
setInterval(pollRoutingStatus, POLL_INTERVAL_MS);
