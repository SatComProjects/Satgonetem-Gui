/** Pure ground-station preset selection helpers. */

export function stationKey(presetName, stationIndex) {
  return `${presetName}:${stationIndex}`;
}

export function buildStationMap(presets) {
  const map = new Map();
  for (const preset of presets) {
    for (const station of preset.stations || []) {
      map.set(stationKey(preset.name, station.index), {
        ...station,
        preset: preset.name,
      });
    }
  }
  return map;
}

export function selectedStations(selectedKeys, stationMap) {
  const result = [];
  for (const key of selectedKeys) {
    const station = stationMap.get(key);
    if (!station) continue;
    const { preset: _preset, ...rest } = station;
    result.push(rest);
  }
  return result;
}

export function mergeStations(existing, incoming) {
  const merged = new Map();
  for (const station of [...(existing || []), ...(incoming || [])]) {
    const key = [
      station.index,
      station.name,
      station.latitude,
      station.longitude,
      station.elevation_m,
    ].join("|");
    merged.set(key, station);
  }
  return [...merged.values()];
}

export function selectionSummary(selectedKeys, presetName, stations) {
  if (stations.length === 0) return "none";
  let selected = 0;
  for (const station of stations) {
    if (selectedKeys.has(stationKey(presetName, station.index))) selected += 1;
  }
  if (selected === 0) return "none";
  return selected === stations.length ? "all" : "some";
}

export function setPresetSelection(
  selectedKeys,
  presetName,
  stations,
  checked,
) {
  const next = new Set(selectedKeys);
  for (const station of stations) {
    const key = stationKey(presetName, station.index);
    if (checked) next.add(key);
    else next.delete(key);
  }
  return next;
}
