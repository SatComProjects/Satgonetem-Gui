/** Phase-1 scenario builder: header, Walker shells, and ground stations. */
import {
  addShell,
  addStation,
  buildScenarioYaml,
  defaultBuilderState,
  removeShell,
  removeStation,
  validateBuilder,
} from "./scenario_builder_model.js?v=1";

let state = defaultBuilderState();

function byId(id) {
  return document.getElementById(id);
}

function setMessage(text, isError = false) {
  const element = byId("sb-msg");
  if (!element) return;
  element.textContent = text;
  element.style.color = isError ? "var(--bad)" : "var(--muted)";
}

function field(labelText, name, type, value) {
  const label = document.createElement("label");
  label.textContent = labelText;
  const input = document.createElement("input");
  input.type = type;
  input.dataset.field = name;
  input.value = value ?? "";
  if (type === "number") input.step = "any";
  label.appendChild(input);
  return label;
}

function patternField(value) {
  const label = document.createElement("label");
  label.textContent = "Pattern";
  const select = document.createElement("select");
  select.dataset.field = "pattern";
  for (const pattern of ["star", "delta"]) {
    const option = document.createElement("option");
    option.value = pattern;
    option.textContent = pattern;
    select.appendChild(option);
  }
  select.value = value || "star";
  label.appendChild(select);
  return label;
}

function removeButton(action, index, label) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "button small secondary sb-remove";
  button.dataset.action = action;
  button.dataset.index = String(index);
  button.textContent = "Remove";
  button.setAttribute("aria-label", `Remove ${label}`);
  return button;
}

function shellRow(shell, index) {
  const row = document.createElement("div");
  row.className = "sb-row sb-shell";
  row.dataset.index = String(index);
  row.append(
    field("Identifier", "identifier", "text", shell.identifier),
    field("Planes", "planes", "number", shell.planes),
    field(
      "Sats/plane",
      "satellites_per_plane",
      "number",
      shell.satellites_per_plane,
    ),
    field("Inclination", "inclination_deg", "number", shell.inclination_deg),
    field("Revs/day", "revs_per_day", "number", shell.revs_per_day),
    patternField(shell.pattern),
    removeButton("remove-shell", index, shell.identifier || `shell ${index + 1}`),
  );
  return row;
}

function stationRow(station, index) {
  const row = document.createElement("div");
  row.className = "sb-row sb-station";
  row.dataset.index = String(index);
  row.append(
    field("Name", "name", "text", station.name),
    field("Latitude", "latitude", "number", station.latitude),
    field("Longitude", "longitude", "number", station.longitude),
    field("Elevation (km)", "elevation_km", "number", station.elevation_km),
    removeButton(
      "remove-station",
      index,
      station.name || `station ${index + 1}`,
    ),
  );
  return row;
}

function renderRows() {
  const shells = byId("sb-shells");
  const stations = byId("sb-stations");
  if (shells) {
    shells.replaceChildren();
    state.shells.forEach((shell, index) => {
      shells.appendChild(shellRow(shell, index));
    });
  }
  if (stations) {
    stations.replaceChildren();
    state.stations.forEach((station, index) => {
      stations.appendChild(stationRow(station, index));
    });
  }
}

function syncHeader() {
  const values = {
    "sb-name": state.name,
    "sb-duration": state.duration_s,
    "sb-tick": state.tick_s,
    "sb-metrics": state.metrics_interval_s,
    "sb-routing": state.routing,
  };
  for (const [id, value] of Object.entries(values)) {
    const element = byId(id);
    if (element) element.value = value;
  }
  const connectivity = byId("sb-connectivity");
  if (connectivity) connectivity.checked = state.connectivity;
}

function numberAt(element) {
  const value = Number(element?.value);
  return Number.isFinite(value) ? value : 0;
}

function collectAll() {
  const shells = [...document.querySelectorAll("#sb-shells .sb-shell")].map(
    (row) => {
      const value = (fieldName) =>
        row.querySelector(`[data-field="${fieldName}"]`)?.value ?? "";
      return {
        identifier: value("identifier"),
        planes: numberAt(row.querySelector('[data-field="planes"]')),
        satellites_per_plane: numberAt(
          row.querySelector('[data-field="satellites_per_plane"]'),
        ),
        inclination_deg: numberAt(
          row.querySelector('[data-field="inclination_deg"]'),
        ),
        revs_per_day: numberAt(row.querySelector('[data-field="revs_per_day"]')),
        pattern: value("pattern") || "star",
      };
    },
  );
  const stations = [...document.querySelectorAll("#sb-stations .sb-station")].map(
    (row) => {
      const value = (fieldName) =>
        row.querySelector(`[data-field="${fieldName}"]`)?.value ?? "";
      return {
        name: value("name"),
        latitude: numberAt(row.querySelector('[data-field="latitude"]')),
        longitude: numberAt(row.querySelector('[data-field="longitude"]')),
        elevation_km: numberAt(row.querySelector('[data-field="elevation_km"]')),
      };
    },
  );
  return {
    name: byId("sb-name")?.value ?? "",
    duration_s: numberAt(byId("sb-duration")),
    tick_s: numberAt(byId("sb-tick")),
    routing: byId("sb-routing")?.value || "static",
    metrics_interval_s: numberAt(byId("sb-metrics")),
    connectivity: Boolean(byId("sb-connectivity")?.checked),
    shells,
    stations,
  };
}

function toggleBuilder() {
  const body = byId("sb-body");
  const button = byId("sb-toggle");
  if (!body || !button) return;
  body.hidden = !body.hidden;
  button.setAttribute("aria-expanded", String(!body.hidden));
  button.textContent = body.hidden ? "Show builder" : "Hide builder";
}

function addShellRow() {
  state = addShell(collectAll());
  renderRows();
  setMessage("");
}

function addStationRow() {
  state = addStation(collectAll());
  renderRows();
  setMessage("");
}

function removeRow(action, index) {
  state = collectAll();
  if (action === "remove-shell") {
    if (state.shells.length <= 1) {
      setMessage("Keep at least one shell.", true);
      return;
    }
    state = removeShell(state, index);
  } else {
    if (state.stations.length <= 1) {
      setMessage("Keep at least one ground station.", true);
      return;
    }
    state = removeStation(state, index);
  }
  renderRows();
  setMessage("");
}

function generate() {
  state = collectAll();
  const errors = validateBuilder(state);
  if (errors.length) {
    setMessage(errors.join(" "), true);
    return;
  }
  const textarea = byId("experiment-scenario");
  if (!textarea) {
    setMessage("The scenario editor is unavailable.", true);
    return;
  }
  textarea.value = buildScenarioYaml(state);
  setMessage("Generated scenario YAML. Review it, then run the experiment.");
}

byId("sb-toggle")?.addEventListener("click", toggleBuilder);
byId("sb-add-shell")?.addEventListener("click", addShellRow);
byId("sb-add-station")?.addEventListener("click", addStationRow);
byId("sb-generate")?.addEventListener("click", generate);

for (const id of ["sb-name", "sb-duration", "sb-tick", "sb-metrics", "sb-routing", "sb-connectivity"]) {
  byId(id)?.addEventListener("input", () => {
    state = collectAll();
  });
}

for (const containerId of ["sb-shells", "sb-stations"]) {
  const container = byId(containerId);
  container?.addEventListener("input", () => {
    state = collectAll();
  });
  container?.addEventListener("change", () => {
    state = collectAll();
  });
  container?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-action]");
    if (!button) return;
    removeRow(button.dataset.action, Number(button.dataset.index));
  });
}

syncHeader();
renderRows();
