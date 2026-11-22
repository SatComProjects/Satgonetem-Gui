/** Topology health card controller for the Nodes page. */
import { api } from "./api.js?v=4";
import { escapeHtml } from "./escape.js";
import {
  formatItemCount,
  healthSummary,
  nonEmptyChecks,
  severityLabel,
} from "./topology_health_model.js?v=1";

let busy = false;
let projectLoaded = false;

function byId(id) {
  return document.getElementById(id);
}

function setMessage(text, isError = false) {
  const element = byId("topology-health-msg");
  if (!element) return;
  element.textContent = text;
  element.style.color = isError ? "var(--bad)" : "var(--muted)";
}

function exportButtons() {
  return [...document.querySelectorAll("[data-topology-export]")];
}

function setExportsEnabled(enabled) {
  for (const button of exportButtons()) button.disabled = !enabled;
}

function checkRow(check) {
  const items = Array.isArray(check.items) ? check.items : [];
  const severity = check.severity === "warning" ? "warning" : "info";
  const preview = items.length
    ? `<p class="muted topo-check-items">${items.map((item) => escapeHtml(item)).join(", ")}</p>`
    : "";
  return `
    <li class="topo-check" data-severity="${severity}">
      <span class="topo-check-badge">${escapeHtml(severityLabel(severity))}</span>
      <div class="topo-check-body">
        <strong>${escapeHtml(check.message || check.id)}</strong>
        ${preview}
      </div>
      <span class="topo-check-count">${escapeHtml(formatItemCount(check.count))}</span>
    </li>`;
}

function renderHealth(health) {
  const summary = byId("topology-health-summary");
  if (summary) summary.textContent = healthSummary(health);
  const list = byId("topology-health-checks");
  const rows = nonEmptyChecks(health.checks);
  if (list) list.innerHTML = rows.map(checkRow).join("");
  const empty = byId("topology-health-empty");
  if (empty) empty.hidden = rows.length > 0;
  setMessage(
    health.healthy
      ? "No warning-level structural findings."
      : "Warning-level findings need attention.",
    !health.healthy,
  );
}

async function loadHealth() {
  try {
    const health = await api.get("/api/topology/health");
    projectLoaded = true;
    setExportsEnabled(true);
    renderHealth(health);
  } catch (error) {
    projectLoaded = false;
    setExportsEnabled(false);
    const message = error.message || "Could not inspect topology health.";
    setMessage(
      error.status === 404
        ? "Load a project to inspect topology health."
        : message,
      true,
    );
  }
}

async function exportTopology(format, button) {
  if (busy || !projectLoaded) return;
  busy = true;
  setExportsEnabled(false);
  if (button) button.disabled = true;
  setMessage(`Preparing ${format.toUpperCase()} export...`);
  try {
    const data = await api.get(
      `/api/topology/export?format=${encodeURIComponent(format)}`,
      { timeout: 60000 },
    );
    const blob = new Blob([data.content], {
      type: data.content_type || "text/plain",
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = data.filename || `topology.${format}`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
    setMessage(`Downloaded ${data.filename || format}.`);
  } catch (error) {
    setMessage(
      error.message || "Could not export the topology.",
      true,
    );
  } finally {
    busy = false;
    setExportsEnabled(projectLoaded);
  }
}

for (const button of exportButtons()) {
  button.addEventListener("click", () => {
    exportTopology(button.dataset.topologyExport, button);
  });
}

loadHealth();
