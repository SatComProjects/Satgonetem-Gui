/** Traffic Generator UI controller. */
import { api } from "./api.js?v=4";
// Keep this queue.js version in sync with the script tag in templates/base.html.
import { jqAdd, jqStartNow, jqStartOne } from "./queue.js?v=22";
import { buildTrafficPayload } from "./traffic_model.js";
import {
  addressabilityCheckboxState,
  addressabilitySummary,
  routingRefreshMessage,
} from "./addressability_model.js?v=1";

function byId(id) {
  return document.getElementById(id);
}

function setMsg(text, isError = false) {
  const element = byId("tg-msg");
  if (!element) return;
  element.textContent = text;
  element.style.color = isError ? "var(--bad)" : "var(--muted)";
}

function toggleTool() {
  const tool = byId("tg-tool").value;
  byId("tg-iperf3-opts").style.display = tool === "iperf3" ? "block" : "none";
  byId("tg-ping-opts").style.display = tool === "ping" ? "block" : "none";
  byId("tg-hping3-opts").style.display = tool === "hping3" ? "block" : "none";
}

function toggleProtocol() {
  const protocol = byId("tg-proto").value;
  byId("tg-tcp-opts").style.display = protocol === "TCP" ? "flex" : "none";
  byId("tg-udp-opts").style.display = protocol === "UDP" ? "flex" : "none";
}

function toggleHpingRate() {
  const rate = byId("tg-hping-rate").value;
  byId("tg-hping-interval-wrap").style.display =
    rate === "interval" ? "flex" : "none";
}

function addOptions(select, nodes) {
  select.replaceChildren();
  for (const node of nodes) {
    const option = document.createElement("option");
    option.value = node.name;
    option.textContent = node.label || node.name;
    select.appendChild(option);
  }
}

async function loadNodes() {
  try {
    const data = await api.get("/api/traffic/nodes");
    const nodes = Array.isArray(data?.nodes) ? data.nodes : [];
    const source = byId("tg-src");
    const destination = byId("tg-dst");
    addOptions(source, nodes);
    addOptions(destination, nodes);
    if (nodes.length > 1) destination.value = nodes[1].name;
  } catch (error) {
    setMsg(error.message || "Could not load traffic nodes.", true);
  }
}

let addressabilityBusy = false;

async function loadAddressability() {
  const checkbox = byId("tg-satellites");
  const count = byId("tg-addressability-count");
  if (!checkbox || !count) return;

  try {
    const data = await api.get("/api/satellites/addressable");
    const state = addressabilityCheckboxState(data.count, data.total);
    checkbox.checked = state.checked;
    checkbox.indeterminate = state.indeterminate;
    checkbox.disabled = addressabilityBusy || state.disabled;
    count.textContent = addressabilitySummary(data.count, data.total);

    const note = byId("tg-addressability-note");
    if (note && !note.textContent && data.routing_refresh_required) {
      note.textContent =
        "Routing is active; re-apply it after changing satellite endpoints.";
    }
  } catch {
    checkbox.checked = false;
    checkbox.indeterminate = false;
    checkbox.disabled = true;
    count.textContent = "Load a project to manage satellite endpoints.";
    const note = byId("tg-addressability-note");
    if (note) note.textContent = "";
  }
}

async function toggleAddressability() {
  const checkbox = byId("tg-satellites");
  if (!checkbox || addressabilityBusy) return;

  addressabilityBusy = true;
  checkbox.disabled = true;
  const note = byId("tg-addressability-note");
  if (note) note.textContent = "";
  const enabling = checkbox.checked;
  setMsg(enabling ? "Enabling satellite endpoints..." : "Disabling satellite endpoints...");

  try {
    const data = await api.post("/api/satellites/addressable", {
      enabled: enabling,
    });
    if (note) note.textContent = routingRefreshMessage(data.routing_refresh_required);
    setMsg("");
    await loadNodes();
  } catch (error) {
    setMsg(error.message || "Could not update satellite endpoints.", true);
  } finally {
    addressabilityBusy = false;
    await loadAddressability();
  }
}

function formFields() {
  return {
    tool: byId("tg-tool").value,
    src: byId("tg-src").value,
    dst: byId("tg-dst").value,
    delay: byId("tg-delay").value,
    protocol: byId("tg-proto").value,
    duration: byId("tg-duration").value,
    port: byId("tg-port").value,
    bandwidthMbps: byId("tg-bandwidth").value,
    parallel: byId("tg-parallel").value,
    interval: byId("tg-interval").value,
    congestionControl: byId("tg-cc").value,
    windowSize: byId("tg-window").value,
    bidir: byId("tg-bidir").checked,
    bidirUdp: byId("tg-bidir-udp").checked,
    pingCount: byId("tg-ping-count").value,
    pingTimeout: byId("tg-ping-timeout").value,
    pingInterval: byId("tg-ping-interval").value,
    pingSize: byId("tg-ping-size").value,
    hpingProto: byId("tg-hping-proto").value,
    hpingDport: byId("tg-hping-dport").value,
    hpingCount: byId("tg-hping-count").value,
    hpingSize: byId("tg-hping-size").value,
    hpingRate: byId("tg-hping-rate").value,
    hpingInterval: byId("tg-hping-interval").value,
    hpingFlags: [],
  };
}

function addToQueue() {
  const item = buildTrafficPayload(formFields());
  if (!item.payload.src || !item.payload.dst) {
    setMsg("Select source and destination.", true);
    return;
  }
  jqAdd(item);
  setMsg("Added to queue.");
}

let runNowBusy = false;

async function runNow() {
  if (runNowBusy) return;
  const item = buildTrafficPayload(formFields());
  if (!item.payload.src || !item.payload.dst) {
    setMsg("Select source and destination.", true);
    return;
  }
  runNowBusy = true;
  const button = byId("tg-run-now");
  if (button) button.disabled = true;
  try {
    item.delay = 0;
    const id = jqAdd(item);
    setMsg("Starting...");
    const started = await jqStartNow(id);
    setMsg(started ? "Started." : "Start failed; see the queue.", !started);
  } finally {
    runNowBusy = false;
    if (button) button.disabled = false;
  }
}

byId("tg-tool").addEventListener("change", toggleTool);
byId("tg-proto").addEventListener("change", toggleProtocol);
byId("tg-hping-rate").addEventListener("change", toggleHpingRate);
byId("tg-add-queue").addEventListener("click", addToQueue);
byId("tg-run-now").addEventListener("click", runNow);
const satelliteToggle = byId("tg-satellites");
if (satelliteToggle) {
  satelliteToggle.addEventListener("change", toggleAddressability);
}

toggleTool();
toggleProtocol();
toggleHpingRate();
loadNodes();
loadAddressability();
