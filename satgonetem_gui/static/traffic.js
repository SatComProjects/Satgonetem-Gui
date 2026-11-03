/** Traffic Generator UI controller. */
import { api } from "./api.js";
import { jqAdd, jqStartOne } from "./queue.js";
import { buildTrafficPayload } from "./traffic_model.js";

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

async function runNow() {
  const item = buildTrafficPayload(formFields());
  if (!item.payload.src || !item.payload.dst) {
    setMsg("Select source and destination.", true);
    return;
  }
  item.delay = 0;
  const id = jqAdd(item);
  jqStartOne(id);
  setMsg("Started.");
}

byId("tg-tool").addEventListener("change", toggleTool);
byId("tg-proto").addEventListener("change", toggleProtocol);
byId("tg-hping-rate").addEventListener("change", toggleHpingRate);
byId("tg-add-queue").addEventListener("click", addToQueue);
byId("tg-run-now").addEventListener("click", runNow);

toggleTool();
toggleProtocol();
toggleHpingRate();
loadNodes();
