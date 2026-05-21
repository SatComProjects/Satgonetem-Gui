/**
 * Traffic Generator UI controller.
 *
 * Handles node loading, form toggles, and payload building.
 * Job queue lives in queue.js.
 */

let nodes = [];

/* ---------- Init ---------- */

async function init() {
  await loadNodes();
}

async function loadNodes() {
  try {
    const r = await fetch('/api/traffic/nodes');
    const j = await r.json().catch(() => ({}));
    nodes = Array.isArray(j.nodes) ? j.nodes : [];
  } catch (e) {
    nodes = [];
  }
  const src = document.getElementById('tg-src');
  const dst = document.getElementById('tg-dst');
  if (!src || !dst) return;
  const opts = nodes.map(n => `<option value="${escapeHtml(n.name)}">${escapeHtml(n.name)} (${escapeHtml(n.type)})</option>`).join('');
  src.innerHTML = opts;
  dst.innerHTML = opts;
}

/* ---------- Form toggles ---------- */

function tgToggleTool() {
  const tool = document.getElementById('tg-tool').value;
  document.getElementById('tg-iperf3-opts').style.display = tool === 'iperf3' ? 'block' : 'none';
  document.getElementById('tg-ping-opts').style.display = tool === 'ping' ? 'block' : 'none';
  document.getElementById('tg-hping3-opts').style.display = tool === 'hping3' ? 'block' : 'none';
}

function tgToggleProto() {
  const proto = document.getElementById('tg-proto').value;
  document.getElementById('tg-tcp-opts').style.display = proto === 'TCP' ? 'flex' : 'none';
  document.getElementById('tg-udp-opts').style.display = proto === 'UDP' ? 'flex' : 'none';
}

function tgToggleHpingRate() {
  const rate = document.getElementById('tg-hping-rate').value;
  document.getElementById('tg-hping-interval-wrap').style.display = rate === 'interval' ? 'flex' : 'none';
}

/* ---------- Build payload from form ---------- */

function buildPayload() {
  const tool = document.getElementById('tg-tool').value;
  const src = document.getElementById('tg-src').value;
  const dst = document.getElementById('tg-dst').value;
  const delay = parseFloat(document.getElementById('tg-delay').value || '0');
  let payload = { src, dst, delay };
  let label = '';

  if (tool === 'iperf3') {
    payload.protocol = document.getElementById('tg-proto').value;
    payload.duration = parseInt(document.getElementById('tg-duration').value || '10', 10);
    payload.port = parseInt(document.getElementById('tg-port').value || '5201', 10);
    payload.bandwidth_mbps = parseFloat(document.getElementById('tg-bandwidth').value || '0');
    payload.parallel = parseInt(document.getElementById('tg-parallel').value || '1', 10);
    payload.interval = parseFloat(document.getElementById('tg-interval').value || '1');
    if (payload.protocol === 'TCP') {
      payload.congestion_control = document.getElementById('tg-cc').value;
      payload.window_size = document.getElementById('tg-window').value || '';
      payload.bidir = document.getElementById('tg-bidir').checked;
    } else {
      payload.bidir = document.getElementById('tg-bidir-udp').checked;
    }
    label = `iperf3 ${src} -> ${dst} (${payload.protocol})`;
  } else if (tool === 'ping') {
    payload.count = parseInt(document.getElementById('tg-ping-count').value || '10', 10);
    payload.timeout_sec = parseFloat(document.getElementById('tg-ping-timeout').value || '1');
    payload.interval_sec = parseFloat(document.getElementById('tg-ping-interval').value || '0.2');
    payload.packet_size = parseInt(document.getElementById('tg-ping-size').value || '56', 10);
    label = `ping ${src} -> ${dst} (${payload.count})`;
  } else if (tool === 'hping3') {
    payload.proto = document.getElementById('tg-hping-proto').value;
    payload.dport = parseInt(document.getElementById('tg-hping-dport').value || '80', 10);
    payload.count = parseInt(document.getElementById('tg-hping-count').value || '100', 10);
    payload.size = parseInt(document.getElementById('tg-hping-size').value || '0', 10);
    payload.rate_type = document.getElementById('tg-hping-rate').value;
    if (payload.rate_type === 'interval') {
      payload.interval = document.getElementById('tg-hping-interval').value || '';
    }
    label = `hping3 ${payload.proto} ${src} -> ${dst}`;
  }

  return { kind: tool, payload, label, delay };
}

function tgAddToQueue() {
  const item = buildPayload();
  if (!item.payload.src || !item.payload.dst) {
    setMsg('Select source and destination.');
    return;
  }
  window.jqAdd(item);
  setMsg('Added to queue.');
}

async function tgRunNow() {
  const item = buildPayload();
  if (!item.payload.src || !item.payload.dst) {
    setMsg('Select source and destination.');
    return;
  }
  item.delay = 0;
  const idx = window.jqAdd(item);
  window.jqStartOne(idx);
  setMsg('Started.');
}

function setMsg(text) {
  const el = document.getElementById('tg-msg');
  if (el) el.textContent = text;
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

/* ---------- Boot ---------- */

window.addEventListener('DOMContentLoaded', init);
window.tgToggleTool = tgToggleTool;
window.tgToggleProto = tgToggleProto;
window.tgToggleHpingRate = tgToggleHpingRate;
window.tgAddToQueue = tgAddToQueue;
window.tgRunNow = tgRunNow;
