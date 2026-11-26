/** Coverage analytics page controller. */
import { api } from "./api.js?v=4";
import { byId, setStatus } from "./dom.js";
import { escapeHtml } from "./escape.js";
import {
  coverageClass,
  coverageNotes,
  coverageSummary,
  formatCount,
  formatCoverage,
  formatDuration,
  formatElevation,
  sortGroundStations,
} from "./coverage_model.js?v=1";

let busy = false;

function setMessage(text, isError = false) {
  setStatus(byId("coverage-msg"), text, isError);
}

function setHidden(element, hidden) {
  if (element) element.hidden = hidden;
}

function syncElevationLabel() {
  const input = byId("coverage-elevation");
  const output = byId("coverage-elevation-value");
  if (!input || !output) return;
  output.textContent = `${input.value}\u00b0`;
}

function shellRow(shell) {
  const percent = Number(shell?.coverage_percent);
  const value = Number.isFinite(percent) ? Math.min(100, Math.max(0, percent)) : 0;
  const satellites = Number(shell?.satellites);
  return `
    <div class="cov-shell">
      <span class="cov-shell-name">${escapeHtml(shell?.identifier || "Unassigned")}</span>
      <progress class="cov-bar" max="100" value="${value}" aria-label="${escapeHtml(shell?.identifier || "Shell")} coverage">${formatCoverage(percent)}</progress>
      <span class="cov-shell-value">${escapeHtml(formatCoverage(percent))}</span>
      <span class="muted cov-shell-count">${Number.isFinite(satellites) ? `${formatCount(satellites)} satellite${satellites === 1 ? "" : "s"}` : "\u2014"}</span>
    </div>`;
}

function stationRow(station) {
  const covered = station?.covered === true;
  return `
    <tr>
      <td>${escapeHtml(station?.name || "\u2014")}</td>
      <td><span class="cov-badge" data-covered="${covered ? "true" : "false"}">${covered ? "Covered" : "Uncovered"}</span></td>
      <td>${escapeHtml(station?.best_satellite || "\u2014")}</td>
      <td>${escapeHtml(formatElevation(station?.best_elevation_deg))}</td>
    </tr>`;
}

function renderShells(shells) {
  const list = byId("coverage-shells-list");
  const empty = byId("coverage-shells-empty");
  const records = Array.isArray(shells) ? shells : [];
  if (list) list.innerHTML = records.map(shellRow).join("");
  setHidden(empty, records.length > 0);
}

function renderStations(stations) {
  const container = byId("coverage-stations-table");
  const empty = byId("coverage-stations-empty");
  const records = sortGroundStations(stations);
  if (!records.length) {
    if (container) container.innerHTML = "";
    setHidden(empty, false);
    return;
  }
  const rows = records.map(stationRow).join("");
  if (container) {
    container.innerHTML = `<table class="cov-table">
      <thead><tr><th scope="col">Station</th><th scope="col">Status</th><th scope="col">Best satellite</th><th scope="col">Elevation</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
  }
  setHidden(empty, true);
}

function renderResult(result) {
  setHidden(byId("coverage-empty"), true);
  setHidden(byId("coverage-results"), false);

  const percent = byId("coverage-percent");
  if (percent) {
    percent.textContent = formatCoverage(result.coverage_percent);
    percent.dataset.level = coverageClass(result.coverage_percent);
  }
  const summary = byId("coverage-summary");
  if (summary) summary.textContent = coverageSummary(result);
  const notes = byId("coverage-notes");
  if (notes) {
    const noteText = coverageNotes(result);
    notes.textContent = noteText;
    setHidden(notes, !noteText);
  }
  renderShells(result.shells);
  renderStations(result.ground_stations);
}

function resetResult() {
  setHidden(byId("coverage-results"), true);
  setHidden(byId("coverage-empty"), false);
  const list = byId("coverage-shells-list");
  if (list) list.innerHTML = "";
  const table = byId("coverage-stations-table");
  if (table) table.innerHTML = "";
  const percent = byId("coverage-percent");
  if (percent) percent.textContent = "\u2014";
}

async function runCoverage() {
  if (busy) return;
  busy = true;
  const button = byId("coverage-run");
  if (button) button.disabled = true;
  setMessage("Analyzing coverage...");
  resetResult();
  const body = {
    elevation_deg: Number(byId("coverage-elevation")?.value ?? 10),
    grid_resolution_deg: Number(byId("coverage-resolution")?.value ?? 1),
    include_shells: byId("coverage-shells")?.checked ?? true,
    include_ground_stations: byId("coverage-stations")?.checked ?? true,
  };
  try {
    const result = await api.post("/api/analysis/coverage", body, {
      timeout: 120000,
    });
    renderResult(result);
    setMessage(
      `Snapshot at step ${result.step} in ${formatDuration(result.duration_ms)}.`,
    );
  } catch (error) {
    setMessage(
      error.message || "Coverage analysis failed.",
      true,
    );
  } finally {
    busy = false;
    if (button) button.disabled = false;
  }
}

byId("coverage-elevation")?.addEventListener("input", syncElevationLabel);
byId("coverage-run")?.addEventListener("click", runCoverage);

syncElevationLabel();
resetResult();
