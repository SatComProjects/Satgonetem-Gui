/** Pure scenario-builder state, validation, and YAML generation. */

export const SHELL_DEFAULTS = {
  identifier: "LEO",
  planes: 3,
  satellites_per_plane: 4,
  inclination_deg: 53,
  revs_per_day: 15.5,
  pattern: "star",
};

export const STATION_DEFAULTS = {
  name: "Berlin",
  latitude: 52.52,
  longitude: 13.405,
  elevation_km: 0.034,
};

export function defaultBuilderState() {
  return {
    name: "Demo Experiment",
    duration_s: 30,
    tick_s: 1,
    routing: "static",
    metrics_interval_s: 5,
    connectivity: false,
    shells: [{ ...SHELL_DEFAULTS }],
    stations: [{ ...STATION_DEFAULTS }],
  };
}

function copyState(state) {
  return {
    ...state,
    shells: (state.shells || []).map((shell) => ({ ...shell })),
    stations: (state.stations || []).map((station) => ({ ...station })),
  };
}

function nextName(existing, base) {
  const names = new Set(existing);
  if (!names.has(base)) return base;
  let index = 2;
  while (names.has(`${base}${index}`)) index += 1;
  return `${base}${index}`;
}

export function addShell(state) {
  const next = copyState(state);
  next.shells.push({
    ...SHELL_DEFAULTS,
    identifier: nextName(
      next.shells.map((shell) => shell.identifier),
      "LEO",
    ),
  });
  return next;
}

export function removeShell(state, index) {
  const next = copyState(state);
  next.shells.splice(index, 1);
  return next;
}

export function addStation(state) {
  const next = copyState(state);
  const name = nextName(
    next.stations.map((station) => station.name),
    "Station 2",
  );
  next.stations.push({
    ...STATION_DEFAULTS,
    name,
    latitude: 0,
    longitude: 0,
    elevation_km: 0,
  });
  return next;
}

export function removeStation(state, index) {
  const next = copyState(state);
  next.stations.splice(index, 1);
  return next;
}

function integer(value) {
  const number = Number(value);
  return Number.isInteger(number) ? number : NaN;
}

function numeric(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : NaN;
}

export function validateBuilder(state) {
  const errors = [];
  const name = String(state?.name ?? "").trim();
  if (!name) errors.push("Name is required.");

  const duration = numeric(state?.duration_s);
  if (!Number.isFinite(duration) || duration <= 0) {
    errors.push("Duration must be greater than zero.");
  }
  const tick = integer(state?.tick_s);
  if (!Number.isInteger(tick) || tick < 1) {
    errors.push("Tick must be a positive integer.");
  }
  const metrics = numeric(state?.metrics_interval_s);
  if (!Number.isFinite(metrics) || metrics <= 0) {
    errors.push("Metrics interval must be greater than zero.");
  }
  if (!String(state?.routing ?? "").trim()) {
    errors.push("Routing is required.");
  }

  const shells = Array.isArray(state?.shells) ? state.shells : [];
  if (!shells.length) errors.push("At least one shell is required.");
  const identifiers = new Set();
  let duplicateShells = false;
  shells.forEach((shell, index) => {
    const label = `Shell ${index + 1}`;
    const identifier = String(shell?.identifier ?? "").trim();
    if (!identifier) {
      errors.push(`${label} needs an identifier.`);
    } else if (identifiers.has(identifier)) {
      duplicateShells = true;
    } else {
      identifiers.add(identifier);
    }
    if (!(integer(shell?.planes) >= 1)) {
      errors.push(`${label} planes must be at least 1.`);
    }
    if (!(integer(shell?.satellites_per_plane) >= 1)) {
      errors.push(`${label} satellites per plane must be at least 1.`);
    }
    const inclination = numeric(shell?.inclination_deg);
    if (!Number.isFinite(inclination) || inclination < 0 || inclination > 180) {
      errors.push(`${label} inclination must be between 0 and 180.`);
    }
    const revs = numeric(shell?.revs_per_day);
    if (!Number.isFinite(revs) || revs <= 0) {
      errors.push(`${label} revs per day must be greater than zero.`);
    }
    if (!["star", "delta"].includes(String(shell?.pattern ?? ""))) {
      errors.push(`${label} pattern must be star or delta.`);
    }
  });
  if (duplicateShells) errors.push("Shell identifiers must be unique.");

  const stations = Array.isArray(state?.stations) ? state.stations : [];
  if (!stations.length) errors.push("At least one ground station is required.");
  const stationNames = new Set();
  let duplicateStations = false;
  stations.forEach((station, index) => {
    const label = `Station ${index + 1}`;
    const stationName = String(station?.name ?? "").trim();
    if (!stationName) {
      errors.push(`${label} needs a name.`);
    } else if (stationNames.has(stationName)) {
      duplicateStations = true;
    } else {
      stationNames.add(stationName);
    }
    const latitude = numeric(station?.latitude);
    if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90) {
      errors.push(`${label} latitude must be between -90 and 90.`);
    }
    const longitude = numeric(station?.longitude);
    if (!Number.isFinite(longitude) || longitude < -180 || longitude > 180) {
      errors.push(`${label} longitude must be between -180 and 180.`);
    }
    const elevation = numeric(station?.elevation_km);
    if (!Number.isFinite(elevation) || elevation < 0) {
      errors.push(`${label} elevation must be zero or greater.`);
    }
  });
  if (duplicateStations) errors.push("Station names must be unique.");

  return errors;
}

function scalar(value, { alwaysQuote = false } = {}) {
  const text = String(value ?? "").replace(/\r?\n/g, " ").trim();
  const safe = /^[A-Za-z0-9 _.-]+$/.test(text) && !/^[-?:,[\]{}#&*!|>'"%@`]/.test(text);
  if (!alwaysQuote && safe) return text;
  return `'${text.replace(/'/g, "''")}'`;
}

function numberText(value) {
  const number = Number(value);
  return Number.isFinite(number) ? String(number) : "0";
}

export function buildScenarioYaml(state) {
  const lines = [
    `name: ${scalar(state?.name, { alwaysQuote: true })}`,
    `duration_s: ${numberText(state?.duration_s)}`,
    `tick_s: ${numberText(state?.tick_s)}`,
    `routing: ${scalar(state?.routing || "static")}`,
    `metrics_interval_s: ${numberText(state?.metrics_interval_s)}`,
    `connectivity: ${state?.connectivity ? "true" : "false"}`,
    "shells:",
  ];
  for (const shell of state?.shells || []) {
    lines.push(
      `  - identifier: ${scalar(shell?.identifier || "LEO")}`,
      `    planes: ${numberText(shell?.planes)}`,
      `    satellites_per_plane: ${numberText(shell?.satellites_per_plane)}`,
      `    inclination_deg: ${numberText(shell?.inclination_deg)}`,
      `    revs_per_day: ${numberText(shell?.revs_per_day)}`,
      `    pattern: ${scalar(shell?.pattern || "star")}`,
    );
  }
  lines.push("ground_stations:");
  for (const station of state?.stations || []) {
    lines.push(
      `  - name: ${scalar(station?.name || "Station")}`,
      `    latitude: ${numberText(station?.latitude)}`,
      `    longitude: ${numberText(station?.longitude)}`,
      `    elevation_km: ${numberText(station?.elevation_km)}`,
    );
  }
  return `${lines.join("\n")}\n`;
}
