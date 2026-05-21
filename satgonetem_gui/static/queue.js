/**
 * Shared job queue controller.
 *
 * Persists in localStorage, polls running jobs, renders a floating panel,
 * and displays result modals on every page.
 */

/* global Chart */

const JQ_KEY = 'sgnt_traffic_queue';

let jq = { items: [], timers: {} };

/* ---------- Init ---------- */

function queueInit() {
  jqLoad();
  jqRender();
  jqUpdateBadge();
}

function jqLoad() {
  try {
    const s = localStorage.getItem(JQ_KEY);
    const arr = s ? JSON.parse(s) : [];
    jq.items = Array.isArray(arr) ? arr : [];
  } catch {
    jq.items = [];
  }
  jq.items.forEach((it, idx) => {
    if (it.status === 'running' && it.job_id) {
      jqTrack(idx);
    }
  });
}

function jqSave() {
  try {
    localStorage.setItem(JQ_KEY, JSON.stringify(jq.items));
  } catch {}
}

/* ---------- Collapse / Expand ---------- */

function jqToggleCollapsed() {
  const el = document.getElementById('floating-queue');
  if (!el) return;
  el.classList.toggle('collapsed');
  const icon = document.getElementById('jq-toggle-icon');
  if (icon) {
    icon.textContent = el.classList.contains('collapsed') ? '\u25B2' : '\u25BC';
  }
}

function jqExpand() {
  const el = document.getElementById('floating-queue');
  if (!el) return;
  el.classList.remove('collapsed');
  const icon = document.getElementById('jq-toggle-icon');
  if (icon) icon.textContent = '\u25BC';
}

/* ---------- Badge ---------- */

function jqUpdateBadge() {
  const badge = document.getElementById('jq-badge');
  if (!badge) return;
  const active = jq.items.filter(it => it.status === 'queued' || it.status === 'scheduled' || it.status === 'running' || it.status === 'starting').length;
  badge.textContent = String(active);
  badge.style.display = active > 0 ? 'inline-block' : 'none';
}

/* ---------- Rendering ---------- */

function jqRender() {
  const list = document.getElementById('job-queue-list');
  if (!list) return;
  list.innerHTML = '';
  if (!jq.items.length) {
    list.innerHTML = '<div class="muted">No jobs queued.</div>';
    jqUpdateBadge();
    return;
  }
  jq.items.forEach((it, idx) => {
    const el = document.createElement('div');
    el.className = 'queue-item';
    el.innerHTML = `
      <div class="queue-item-header">
        <span class="queue-kind">${escapeHtml(it.kind)}</span>
        <span class="queue-label">${escapeHtml(it.label)}</span>
        <span class="queue-status">${escapeHtml(it.status)}</span>
      </div>
      <div class="queue-item-actions">
        ${it.status === 'done' ? '<button type="button" class="button small secondary" onclick="jqPlot(' + idx + ')">Plot</button>' : ''}
        ${it.status === 'queued' || it.status === 'scheduled' ? '<button type="button" class="button small" onclick="jqStartOne(' + idx + ')">Start</button>' : ''}
        ${it.status === 'running' ? '<button type="button" class="button small secondary" onclick="jqCancel(' + idx + ')">Cancel</button>' : ''}
        <button type="button" class="button small secondary" onclick="jqRemove(' + idx + ')">Remove</button>
      </div>
    `;
    list.appendChild(el);
  });
  jqUpdateBadge();
}

/* ---------- Queue operations ---------- */

function jqAdd(item) {
  item = Object.assign({ id: 'q' + Date.now() + Math.random().toString(16).slice(2), status: 'queued', delay: 0 }, item || {});
  jq.items.push(item);
  jqSave();
  jqRender();
  jqExpand();
  return jq.items.length - 1;
}

function jqRemove(idx) {
  const it = jq.items[idx];
  if (it && jq.timers[it.id]) {
    clearTimeout(jq.timers[it.id]);
    delete jq.timers[it.id];
  }
  jq.items.splice(idx, 1);
  jqSave();
  jqRender();
}

function jqClear() {
  jq.items.forEach(it => {
    if (jq.timers[it.id]) {
      clearTimeout(jq.timers[it.id]);
      delete jq.timers[it.id];
    }
  });
  jq.items = [];
  jqSave();
  jqRender();
}

function jqStartAll() {
  jq.items.forEach((_, i) => jqStartOne(i));
}

function jqStartOne(idx) {
  const it = jq.items[idx];
  if (!it || it.status === 'running' || it.status === 'started') return;
  const delayMs = Math.max(0, (Number(it.delay) || 0) * 1000);
  it.status = delayMs > 0 ? 'scheduled' : 'starting';
  jqSave();
  jqRender();
  if (jq.timers[it.id]) {
    try { clearTimeout(jq.timers[it.id]); } catch {}
  }
  jq.timers[it.id] = setTimeout(() => jqStartNow(idx), delayMs);
}

async function jqStartNow(idx) {
  const it = jq.items[idx];
  if (!it) return;
  it.status = 'starting';
  jqSave();
  jqRender();
  try {
    const r = await fetch('/api/traffic/' + it.kind, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(it.payload || {}),
    });
    const j = await r.json().catch(() => ({ ok: false }));
    if (r.ok && j.ok && j.job_id) {
      it.status = 'running';
      it.job_id = j.job_id;
      jqSave();
      jqRender();
      jqTrack(idx);
    } else {
      it.status = 'error';
      it.error = j.error || 'Start failed';
      jqSave();
      jqRender();
    }
  } catch (e) {
    it.status = 'error';
    it.error = String(e.message || e);
    jqSave();
    jqRender();
  }
}

function jqCancel(idx) {
  const it = jq.items[idx];
  if (!it) return;
  if (it.job_id) {
    fetch('/api/traffic/cancel', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ job_id: it.job_id }),
    }).catch(() => {});
  }
  it.status = 'cancelled';
  jqSave();
  jqRender();
}

/* ---------- Tracking ---------- */

async function jqTrack(idx) {
  const it = jq.items[idx];
  if (!it || !it.job_id) return;
  try {
    const r = await fetch('/api/traffic/status?job_id=' + encodeURIComponent(it.job_id));
    if (!r.ok) throw new Error('status fetch failed');
    const st = await r.json();
    if (st.status === 'done') {
      it.status = 'done';
      it.results = st.results || null;
      jqSave();
      jqRender();
      return;
    }
    if (st.status === 'error') {
      it.status = 'error';
      it.error = st.error || 'Unknown error';
      jqSave();
      jqRender();
      return;
    }
    if (st.status === 'cancelled') {
      it.status = 'cancelled';
      jqSave();
      jqRender();
      return;
    }
    setTimeout(() => jqTrack(idx), 1000);
  } catch (e) {
    setTimeout(() => jqTrack(idx), 1500);
  }
}

/* ---------- Plotting ---------- */

function jqPlot(idx) {
  const it = jq.items[idx];
  if (!it || !it.results) return;
  if (it.kind === 'iperf3') {
    plotIperf3(it);
  } else if (it.kind === 'ping') {
    plotPing(it);
  } else if (it.kind === 'hping3') {
    plotHping3(it);
  }
}

function openModal(titleHtml, bodyHtml) {
  const modal = document.getElementById('results-modal');
  const title = document.getElementById('results-title');
  const body = document.getElementById('results-body');
  if (title) title.textContent = titleHtml;
  if (body) body.innerHTML = bodyHtml;
  if (modal) modal.style.display = 'flex';
}

function closeResults() {
  const modal = document.getElementById('results-modal');
  if (modal) modal.style.display = 'none';
}

function plotIperf3(it) {
  const r = it.results;
  const isTcp = (r.protocol || '').toUpperCase() === 'TCP';
  const isUdp = !isTcp;

  let metricsHtml = '<div class="results-grid">';
  metricsHtml += metricItem('Protocol', r.protocol);
  metricsHtml += metricItem('Duration', fmt(r.duration_seconds) + ' s');
  metricsHtml += metricItem('Avg Throughput', fmt(r.avg_throughput_mbps) + ' Mbps');
  metricsHtml += metricItem('Max Throughput', fmt(r.max_throughput_mbps) + ' Mbps');
  metricsHtml += metricItem('Min Throughput', fmt(r.min_throughput_mbps) + ' Mbps');
  if (isTcp) {
    metricsHtml += metricItem('Total Bytes Sent', fmtBytes(r.total_bytes_sent));
    metricsHtml += metricItem('Total Bytes Received', fmtBytes(r.total_bytes_received));
    metricsHtml += metricItem('Retransmits', r.total_retransmits);
    metricsHtml += metricItem('Avg RTT', fmt(r.avg_rtt_ms) + ' ms');
    metricsHtml += metricItem('Max RTT', fmt(r.max_rtt_ms) + ' ms');
  } else {
    metricsHtml += metricItem('Total Packets', r.total_packets);
    metricsHtml += metricItem('Lost Packets', r.total_lost_packets);
    metricsHtml += metricItem('Avg Loss', fmt(r.avg_loss_percent) + ' %');
    metricsHtml += metricItem('Avg Jitter', fmt(r.avg_jitter_ms) + ' ms');
    metricsHtml += metricItem('Out of Order', r.total_out_of_order);
  }
  if (r.pmtu) {
    metricsHtml += metricItem('Path MTU', r.pmtu + ' bytes');
  }
  metricsHtml += '</div>';

  const chartsHtml = '<div class="chart-grid">' +
    '<div class="chart-container"><canvas id="chart-main-1"></canvas></div>' +
    '<div class="chart-container"><canvas id="chart-aux"></canvas></div>' +
    '<div class="chart-container"><canvas id="chart-main-2"></canvas></div>' +
    '<div class="chart-container"><canvas id="chart-cum"></canvas></div>' +
    (isTcp ? '<div class="chart-container"><canvas id="chart-tput-tcp"></canvas></div>' : '') +
    '</div>';

  openModal(`iperf3 Results - ${it.payload.src} -> ${it.payload.dst}`, metricsHtml + chartsHtml);

  requestAnimationFrame(() => {
    const iv = Array.isArray(r.intervals) ? r.intervals : [];
    const nStreams = iv.reduce((m, entry) => Math.max(m, Array.isArray(entry.streams) ? entry.streams.length : 0), 0);
    const flowColors = ['#ef4444','#22c55e','#eab308','#a78bfa','#f472b6','#60a5fa','#f97316','#84cc16'];

    const times = [];
    const tput = [];
    const cumBits = [];
    const cwnd = [];
    const rtt = [];
    const aux = [];
    const jitter = [];

    const perTput = Array.from({length: nStreams}, () => []);
    const perCwnd = Array.from({length: nStreams}, () => []);
    const perRtt = Array.from({length: nStreams}, () => []);
    const perJit = Array.from({length: nStreams}, () => []);
    const perAux = Array.from({length: nStreams}, () => []);

    let cumulative = 0;
    let tsec = 0;

    iv.forEach((entry) => {
      const sum = entry.sum || {};
      const bps = sum.bits_per_second || 0;
      const bytes = sum.bytes || 0;
      let dt = Number(sum.seconds != null ? sum.seconds : ((sum.end != null && sum.start != null) ? (sum.end - sum.start) : 1));
      if (!isFinite(dt) || dt <= 0) dt = 1;
      tsec += dt;
      cumulative += (bytes || 0) * 8;
      times.push(tsec);
      tput.push(bps / 1e6);
      cumBits.push(cumulative / 1e6);

      if (isTcp) {
        const st = (entry.streams && entry.streams[0]) || {};
        cwnd.push(st.snd_cwnd != null ? st.snd_cwnd / 1024.0 : null);
        rtt.push(st.rtt != null ? st.rtt / 1000.0 : null);
        aux.push(st.retransmits != null ? st.retransmits : 0);
        for (let si = 0; si < nStreams; si++) {
          const s = (entry.streams && entry.streams[si]) || {};
          perTput[si].push(s.bits_per_second != null ? s.bits_per_second / 1e6 : null);
          perCwnd[si].push(s.snd_cwnd != null ? s.snd_cwnd / 1024.0 : null);
          perRtt[si].push(s.rtt != null ? s.rtt / 1000.0 : null);
          perAux[si].push(s.retransmits != null ? s.retransmits : null);
        }
      } else {
        let loss = null;
        if (sum.lost_percent != null) {
          loss = Number(sum.lost_percent);
        } else if (sum.lost_packets != null && sum.packets != null && Number(sum.packets) > 0) {
          loss = (Number(sum.lost_packets) / Number(sum.packets)) * 100.0;
        } else {
          const st0 = (entry.streams && entry.streams[0]) || {};
          if (st0.lost_percent != null) loss = Number(st0.lost_percent);
          else if (st0.lost_packets != null && st0.packets != null && Number(st0.packets) > 0)
            loss = (Number(st0.lost_packets) / Number(st0.packets)) * 100.0;
          else loss = 0;
        }
        aux.push(loss);
        for (let si = 0; si < nStreams; si++) {
          const s = (entry.streams && entry.streams[si]) || {};
          perTput[si].push(s.bits_per_second != null ? s.bits_per_second / 1e6 : null);
          perJit[si].push(s.jitter_ms != null ? s.jitter_ms : null);
          let lp = null;
          if (s.lost_percent != null) lp = Number(s.lost_percent);
          else if (s.lost_packets != null && s.packets != null && Number(s.packets) > 0)
            lp = (Number(s.lost_packets) / Number(s.packets)) * 100.0;
          perAux[si].push(lp != null ? lp : null);
        }
        let jm = sum.jitter_ms;
        if (jm == null) {
          const st0 = (entry.streams && entry.streams[0]) || {};
          jm = st0.jitter_ms;
        }
        let v = Number(jm || 0);
        if (!isFinite(v) || v <= 0) v = 0.001;
        jitter.push(v);
      }
    });

    function fmtTick(v) { const n = parseFloat(v); return isFinite(n) ? n.toFixed(2) : v; }
    function mkFlowDs(dataArr, labelPrefix) {
      return dataArr.map((arr, i) => ({
        label: `${labelPrefix} ${i+1}`,
        data: arr,
        borderColor: flowColors[i % flowColors.length],
        tension: 0.2,
        borderDash: [6, 4],
        pointRadius: 0,
      }));
    }

    const axesPrimary = { responsive: true, animation: false, scales: { x: { title: { display: true, text: 'Time (s)' }, grid: { color: '#1e2937' }, ticks: { callback: fmtTick } }, y: { beginAtZero: true, title: { display: true, text: isTcp ? 'KB' : 'Mbps' }, grid: { color: '#1e2937' } } }, plugins: { legend: { display: true } } };
    const axesAux = { responsive: true, animation: false, scales: { x: { title: { display: true, text: 'Time (s)' }, grid: { color: '#1e2937' }, ticks: { callback: fmtTick } }, y: { beginAtZero: true, title: { display: true, text: isUdp ? '%' : 'Count' }, grid: { color: '#1e2937' } } }, plugins: { legend: { display: true } } };
    const axesRtt = { responsive: true, animation: false, scales: { x: { title: { display: true, text: 'Time (s)' }, grid: { color: '#1e2937' }, ticks: { callback: fmtTick } }, y: { beginAtZero: true, title: { display: true, text: 'ms' }, grid: { color: '#1e2937' } } }, plugins: { legend: { display: true } } };
    const axesCum = { responsive: true, animation: false, scales: { x: { title: { display: true, text: 'Time (s)' }, grid: { color: '#1e2937' }, ticks: { callback: fmtTick } }, y: { beginAtZero: true, title: { display: true, text: 'Mbit' }, grid: { color: '#1e2937' } } }, plugins: { legend: { display: true } } };
    const axesJit = { responsive: true, animation: false, scales: { x: { title: { display: true, text: 'Time (s)' }, grid: { color: '#1e2937' }, ticks: { callback: fmtTick } }, y: { type: 'logarithmic', title: { display: true, text: 'Jitter (ms, log)' }, grid: { color: '#1e2937' } } }, plugins: { legend: { display: true } } };
    const axesTput = { responsive: true, animation: false, scales: { x: { title: { display: true, text: 'Time (s)' }, grid: { color: '#1e2937' }, ticks: { callback: fmtTick } }, y: { beginAtZero: true, title: { display: true, text: 'Mbps' }, grid: { color: '#1e2937' } } }, plugins: { legend: { display: true } } };

    const ctx1 = document.getElementById('chart-main-1');
    if (ctx1 && window.Chart) {
      const base = isTcp
        ? { label: 'CWND (KB)', data: cwnd, borderColor: '#3da9fc', tension: 0.2 }
        : { label: 'Throughput (Mbps)', data: tput, borderColor: '#3da9fc', tension: 0.2 };
      const overlays = isTcp ? mkFlowDs(perCwnd, 'Flow CWND') : mkFlowDs(perTput, 'Flow Mbps');
      new Chart(ctx1, { type: 'line', data: { labels: times, datasets: [base].concat(nStreams > 1 ? overlays : []) }, options: axesPrimary });
    }

    const ctx2 = document.getElementById('chart-aux');
    if (ctx2 && window.Chart) {
      const auxLabel = isUdp ? 'Loss %' : 'Retrans';
      const overlaysAux = mkFlowDs(perAux, isUdp ? 'Flow Loss %' : 'Flow Retrans');
      new Chart(ctx2, { type: 'line', data: { labels: times, datasets: [{ label: auxLabel, data: aux, borderColor: '#f59e0b', tension: 0.2 }].concat(nStreams > 1 ? overlaysAux : []) }, options: axesAux });
    }

    const ctx3 = document.getElementById('chart-main-2');
    if (ctx3 && window.Chart) {
      if (isTcp) {
        const overlaysRtt = mkFlowDs(perRtt, 'Flow RTT');
        new Chart(ctx3, { type: 'line', data: { labels: times, datasets: [{ label: 'RTT (ms)', data: rtt, borderColor: '#10b981', tension: 0.2 }].concat(nStreams > 1 ? overlaysRtt : []) }, options: axesRtt });
      } else {
        const overlaysJit = mkFlowDs(perJit, 'Flow Jitter');
        new Chart(ctx3, { type: 'line', data: { labels: times, datasets: [{ label: 'Jitter (ms)', data: jitter, borderColor: '#22c55e', tension: 0.2 }].concat(nStreams > 1 ? overlaysJit : []) }, options: axesJit });
      }
    }

    const ctxCum = document.getElementById('chart-cum');
    if (ctxCum && window.Chart) {
      new Chart(ctxCum, { type: 'line', data: { labels: times, datasets: [{ label: 'Cumulative Bits (Mbit)', data: cumBits, borderColor: '#a78bfa', tension: 0.2 }] }, options: axesCum });
    }

    if (isTcp) {
      const ctxTput = document.getElementById('chart-tput-tcp');
      if (ctxTput && window.Chart) {
        const overlays = mkFlowDs(perTput, 'Flow Mbps');
        new Chart(ctxTput, { type: 'line', data: { labels: times, datasets: [{ label: 'Throughput (Mbps)', data: tput, borderColor: '#3da9fc', tension: 0.2 }].concat(nStreams > 1 ? overlays : []) }, options: axesTput });
      }
    }
  });
}

function plotPing(it) {
  const r = it.results;
  let html = '<div class="results-grid">';
  html += metricItem('Packets', `${r.packets_received} / ${r.packets_transmitted}`);
  html += metricItem('Loss', fmt(r.packet_loss_percent) + ' %');
  html += metricItem('Reachable', r.reachable ? 'Yes' : 'No');
  html += metricItem('RTT min', fmt(r.rtt_min_ms) + ' ms');
  html += metricItem('RTT avg', fmt(r.rtt_avg_ms) + ' ms');
  html += metricItem('RTT max', fmt(r.rtt_max_ms) + ' ms');
  html += metricItem('RTT mdev', fmt(r.rtt_mdev_ms) + ' ms');
  html += '</div>';
  openModal(`Ping Results - ${it.payload.src} -> ${it.payload.dst}`, html);
}

function plotHping3(it) {
  const r = it.results;
  let metricsHtml = '<div class="results-grid">';
  metricsHtml += metricItem('Packets', `${r.packets_received} / ${r.packets_transmitted}`);
  metricsHtml += metricItem('Loss', fmt(r.packet_loss_percent) + ' %');
  metricsHtml += metricItem('Reachable', r.reachable ? 'Yes' : 'No');
  metricsHtml += metricItem('RTT min', fmt(r.rtt_min_ms) + ' ms');
  metricsHtml += metricItem('RTT avg', fmt(r.rtt_avg_ms) + ' ms');
  metricsHtml += metricItem('RTT max', fmt(r.rtt_max_ms) + ' ms');
  metricsHtml += '</div>';

  const chartsHtml = '<div class="chart-grid">' +
    '<div class="chart-container"><canvas id="chart-hping-rtt"></canvas></div>' +
    '<div class="chart-container"><canvas id="chart-hping-cum"></canvas></div>' +
    '</div>';

  openModal(`hping3 Results - ${it.payload.src} -> ${it.payload.dst}`, metricsHtml + chartsHtml);

  requestAnimationFrame(() => {
    const labels = (r.seq || []).map(String);
    newChart('chart-hping-rtt', 'line', labels, [
      { label: 'RTT (ms)', data: r.rtt_ms || [], borderColor: '#3da9fc', tension: 0.2, pointRadius: 2 },
    ]);
    newChart('chart-hping-cum', 'line', labels, [
      { label: 'Cumulative Mbit', data: r.cumulative_mbit || [], borderColor: '#22c55e', tension: 0.2, pointRadius: 2 },
    ]);
  });
}

/* ---------- Chart helpers ---------- */

function newChart(canvasId, type, labels, datasets) {
  const ctx = document.getElementById(canvasId);
  if (!ctx || !window.Chart) return null;
  return new Chart(ctx, {
    type,
    data: { labels, datasets },
    options: {
      responsive: true,
      animation: false,
      plugins: { legend: { display: true } },
      scales: {
        x: { title: { display: true, text: 'Time (s)' }, grid: { color: '#1e2937' } },
        y: { grid: { color: '#1e2937' } },
      },
    },
  });
}

/* ---------- DOM helpers ---------- */

function metricItem(label, value) {
  return `<div class="result-metric"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd></div>`;
}

function fmt(v) {
  if (v == null || v !== v) return '-';
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(2) : String(v);
}

function fmtBytes(b) {
  if (b == null) return '-';
  const n = Number(b);
  if (!Number.isFinite(n)) return '-';
  if (n >= 1e9) return (n / 1e9).toFixed(2) + ' GB';
  if (n >= 1e6) return (n / 1e6).toFixed(2) + ' MB';
  if (n >= 1e3) return (n / 1e3).toFixed(2) + ' KB';
  return n + ' B';
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

/* ---------- Boot ---------- */

window.addEventListener('DOMContentLoaded', queueInit);
window.jqAdd = jqAdd;
window.jqStartAll = jqStartAll;
window.jqClear = jqClear;
window.jqStartOne = jqStartOne;
window.jqRemove = jqRemove;
window.jqCancel = jqCancel;
window.jqPlot = jqPlot;
window.closeResults = closeResults;
window.jqToggleCollapsed = jqToggleCollapsed;
