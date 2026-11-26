/** Link-budget workbench page controller. */
import { api } from "./api.js?v=4";
import { byId, setStatus } from "./dom.js";
import {
  atmosphereNote,
  budgetRows,
  budgetSummary,
  formatCapacity,
} from "./link_budget_model.js?v=1";

let busy = false;

function setMessage(text, isError = false) {
  setStatus(byId("lb-msg"), text, isError);
}

function numberValue(id, fallback = 0) {
  const value = Number(byId(id)?.value);
  return Number.isFinite(value) ? value : fallback;
}

function optionalNumber(id) {
  const raw = byId(id)?.value ?? "";
  if (String(raw).trim() === "") return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

function requestBody() {
  return {
    direction: byId("lb-direction")?.value || "downlink",
    strategy: byId("lb-strategy")?.value || "shannon",
    frequency_ghz: numberValue("lb-frequency", 19),
    bandwidth_mhz: numberValue("lb-bandwidth", 500),
    distance_km: numberValue("lb-distance", 1000),
    elevation_deg: numberValue("lb-elevation", 30),
    gs_latitude: numberValue("lb-gs-lat", 0),
    gs_longitude: numberValue("lb-gs-lon", 0),
    satellite_antenna_diameter_m: numberValue("lb-sat-diameter", 0.5),
    satellite_antenna_efficiency: numberValue("lb-sat-efficiency", 0.6),
    satellite_sspa_output_power_db: numberValue("lb-sat-sspa", 10),
    satellite_losses_db: numberValue("lb-sat-losses", 0),
    satellite_eirp_db: optionalNumber("lb-sat-eirp"),
    ground_antenna_diameter_m: numberValue("lb-gnd-diameter", 1.2),
    ground_antenna_efficiency: numberValue("lb-gnd-efficiency", 0.6),
    ground_losses_db: numberValue("lb-gnd-losses", 0),
    ground_eirp_db: optionalNumber("lb-gnd-eirp"),
    rx_tsys_k: numberValue("lb-tsys", 100),
    unavailability_percent: numberValue("lb-unavailability", 0.1),
  };
}

function renderBreakdown(result) {
  const list = byId("lb-breakdown");
  if (!list) return;
  list.replaceChildren();
  for (const row of budgetRows(result)) {
    const wrapper = document.createElement("div");
    const term = document.createElement("dt");
    term.textContent = row.label;
    const value = document.createElement("dd");
    value.textContent = row.value;
    wrapper.append(term, value);
    list.appendChild(wrapper);
  }
}

function resetResult() {
  if (byId("lb-results")) byId("lb-results").hidden = true;
  if (byId("lb-empty")) byId("lb-empty").hidden = false;
  const capacity = byId("lb-capacity");
  if (capacity) capacity.textContent = "\u2014";
  const summary = byId("lb-summary");
  if (summary) summary.textContent = "";
  const note = byId("lb-atmosphere-note");
  if (note) {
    note.textContent = "";
    note.hidden = true;
  }
  if (byId("lb-breakdown")) byId("lb-breakdown").replaceChildren();
}

function renderResult(result) {
  if (byId("lb-empty")) byId("lb-empty").hidden = true;
  if (byId("lb-results")) byId("lb-results").hidden = false;
  const capacity = byId("lb-capacity");
  if (capacity) capacity.textContent = formatCapacity(result.capacity_kbps);
  const summary = byId("lb-summary");
  if (summary) summary.textContent = budgetSummary(result);
  renderBreakdown(result);
  const note = byId("lb-atmosphere-note");
  if (note) {
    const text = atmosphereNote(result);
    note.textContent = text;
    note.hidden = !text;
  }
}

async function calculate() {
  if (busy) return;
  busy = true;
  const button = byId("lb-run");
  if (button) button.disabled = true;
  setMessage("Calculating link budget...");
  try {
    const result = await api.post(
      "/api/analysis/link-budget",
      requestBody(),
      { timeout: 30000 },
    );
    renderResult(result);
    setMessage("");
  } catch (error) {
    resetResult();
    setMessage(error.message || "Link budget calculation failed.", true);
  } finally {
    busy = false;
    if (button) button.disabled = false;
  }
}

byId("lb-run")?.addEventListener("click", calculate);
byId("lb-direction")?.addEventListener("change", () => {
  const direction = byId("lb-direction")?.value;
  const frequency = byId("lb-frequency");
  if (!frequency) return;
  if (direction === "uplink" && frequency.value === "19") {
    frequency.value = "14.25";
  } else if (direction === "downlink" && frequency.value === "14.25") {
    frequency.value = "19";
  }
});

resetResult();
