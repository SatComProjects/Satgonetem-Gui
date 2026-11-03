/** Ground-station preset selection page. */
import { api } from "./api.js";
import {
  buildStationMap,
  selectedStations,
  setPresetSelection,
  stationKey,
} from "./ground_stations_model.js";

const presetSelect = document.getElementById("preset_select");
const tbody = document.getElementById("station_tbody");
const tableEmpty = document.getElementById("table_empty");
const selectedCount = document.getElementById("selected_count");
const checkAllBox = document.getElementById("check_all");
const customList = document.getElementById("custom_list");

let presets = [];
let currentStations = [];
let currentPresetName = "";
let selectedKeys = new Set();
let customStations = [];
let customNextIdx = 100000;

tableEmpty.style.display = "";
tableEmpty.textContent = "Loading ground-station presets...";

function updateCount() {
  selectedCount.textContent = `${selectedKeys.size + customStations.length} selected`;
}

function renderTable() {
  tbody.replaceChildren();
  if (currentStations.length === 0) {
    tableEmpty.style.display = "";
    return;
  }
  tableEmpty.style.display = "none";

  for (const station of currentStations) {
    const key = stationKey(currentPresetName, station.index);
    const checked = selectedKeys.has(key);
    const row = document.createElement("tr");
    if (checked) row.classList.add("row-selected");

    const checkCell = document.createElement("td");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.dataset.key = key;
    checkbox.checked = checked;
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        selectedKeys.add(key);
        row.classList.add("row-selected");
      } else {
        selectedKeys.delete(key);
        row.classList.remove("row-selected");
      }
      updateCount();
    });
    checkCell.appendChild(checkbox);
    row.appendChild(checkCell);

    for (const value of [
      station.index,
      station.name,
      station.latitude,
      station.longitude,
      station.elevation_km,
    ]) {
      const cell = document.createElement("td");
      cell.textContent = value;
      row.appendChild(cell);
    }
    tbody.appendChild(row);
  }
  updateCount();
}

function loadPreset(index) {
  const preset = presets[index];
  currentStations = preset && Array.isArray(preset.stations) ? preset.stations : [];
  currentPresetName = preset ? preset.name : "";
  renderTable();
}

presetSelect.addEventListener("change", () => {
  loadPreset(parseInt(presetSelect.value, 10));
});

checkAllBox.addEventListener("change", () => {
  selectedKeys = setPresetSelection(
    selectedKeys,
    currentPresetName,
    currentStations,
    checkAllBox.checked,
  );
  renderTable();
});

document.getElementById("select_all_btn").addEventListener("click", () => {
  selectedKeys = setPresetSelection(
    selectedKeys,
    currentPresetName,
    currentStations,
    true,
  );
  renderTable();
});

document.getElementById("deselect_all_btn").addEventListener("click", () => {
  selectedKeys = setPresetSelection(
    selectedKeys,
    currentPresetName,
    currentStations,
    false,
  );
  renderTable();
});

function renderCustomList() {
  customList.replaceChildren();
  for (const [index, station] of customStations.entries()) {
    const item = document.createElement("li");
    const label = document.createElement("span");
    label.textContent = `${station.name} (${station.latitude}, ${station.longitude}, ${station.elevation_km} km)`;
    const remove = document.createElement("button");
    remove.textContent = "Remove";
    remove.type = "button";
    remove.className = "button";
    remove.addEventListener("click", () => {
      customStations.splice(index, 1);
      renderCustomList();
      updateCount();
    });
    item.appendChild(label);
    item.appendChild(remove);
    customList.appendChild(item);
  }
  updateCount();
}

document.getElementById("add_custom_btn").addEventListener("click", () => {
  const name = document.getElementById("c_name").value.trim();
  const latitude = parseFloat(document.getElementById("c_lat").value);
  const longitude = parseFloat(document.getElementById("c_lon").value);
  const elevation = parseFloat(document.getElementById("c_elev").value || "0");
  if (!name || Number.isNaN(latitude) || Number.isNaN(longitude)) {
    alert("Name, latitude, and longitude are required.");
    return;
  }
  customStations.push({
    index: customNextIdx,
    name,
    latitude,
    longitude,
    elevation_km: Number.isNaN(elevation) ? 0 : elevation,
  });
  customNextIdx += 1;
  document.getElementById("c_name").value = "";
  document.getElementById("c_lat").value = "";
  document.getElementById("c_lon").value = "";
  document.getElementById("c_elev").value = "0.0";
  renderCustomList();
});

document.getElementById("apply_btn").addEventListener("click", () => {
  const stationMap = buildStationMap(presets);
  const result = selectedStations(selectedKeys, stationMap).concat(customStations);
  sessionStorage.setItem("satgonetem_gs_pending", JSON.stringify(result));
  window.location.href = "/new_project";
});

async function loadPresets() {
  try {
    presets = await api.get("/api/ground_stations/presets");
    if (!Array.isArray(presets)) presets = [];
    for (const [index, preset] of presets.entries()) {
      const option = document.createElement("option");
      option.value = String(index);
      option.textContent = preset.name;
      presetSelect.appendChild(option);
    }
    if (presets.length > 0) loadPreset(0);
  } catch (error) {
    tableEmpty.style.display = "";
    tableEmpty.textContent = error.message || "Failed to load presets.";
  }
}

loadPresets();
