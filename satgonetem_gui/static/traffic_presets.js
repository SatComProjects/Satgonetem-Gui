/** Pure helpers for browser-local traffic presets. */

export const PRESETS_KEY = "sgnt_traffic_presets";
export const PRESETS_VERSION = 1;
export const MAX_PRESETS = 20;
export const MAX_NAME_LENGTH = 60;

const TOOLS = new Set(["iperf3", "ping", "hping3"]);

export function normalizePresetName(name) {
  return String(name ?? "")
    .trim()
    .replace(/\s+/g, " ")
    .slice(0, MAX_NAME_LENGTH);
}

function cleanFields(fields) {
  if (!fields || typeof fields !== "object") return null;
  const tool = TOOLS.has(fields.tool) ? fields.tool : null;
  if (!tool) return null;
  const src = typeof fields.src === "string" ? fields.src : "";
  const dst = typeof fields.dst === "string" ? fields.dst : "";
  if (!src || !dst) return null;
  return { ...fields, tool, src, dst };
}

/**
 * Build one validated preset from a name and raw form fields.
 * @returns {{name: string, fields: object}|null}
 */
export function presetFromFields(name, fields) {
  const cleanName = normalizePresetName(name);
  const clean = cleanFields(fields);
  if (!cleanName || !clean) return null;
  return { name: cleanName, fields: clean };
}

/** Accept the stored envelope or a bare array and drop malformed entries. */
export function normalizePresets(raw) {
  const source = Array.isArray(raw)
    ? raw
    : raw && typeof raw === "object" && Array.isArray(raw.presets)
      ? raw.presets
      : [];
  const presets = [];
  const seen = new Set();
  for (const entry of source) {
    if (!entry || typeof entry !== "object") continue;
    const name = normalizePresetName(entry.name);
    const fields = cleanFields(entry.fields);
    if (!name || !fields) continue;
    const key = name.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    presets.push({ name, fields });
    if (presets.length >= MAX_PRESETS) break;
  }
  return { version: PRESETS_VERSION, presets };
}

export function findPreset(collection, name) {
  const key = normalizePresetName(name).toLowerCase();
  if (!key) return null;
  return (
    normalizePresets(collection).presets.find(
      (preset) => preset.name.toLowerCase() === key,
    ) || null
  );
}

/** Insert or replace by case-insensitive name, dropping the oldest at the cap. */
export function upsertPreset(collection, preset) {
  const base = normalizePresets(collection);
  const clean = presetFromFields(preset?.name, preset?.fields);
  if (!clean) return base;
  const key = clean.name.toLowerCase();
  const index = base.presets.findIndex(
    (entry) => entry.name.toLowerCase() === key,
  );
  const presets = [...base.presets];
  if (index >= 0) presets[index] = clean;
  else presets.push(clean);
  return { version: PRESETS_VERSION, presets: presets.slice(-MAX_PRESETS) };
}

export function removePreset(collection, name) {
  const key = normalizePresetName(name).toLowerCase();
  const base = normalizePresets(collection);
  return {
    version: PRESETS_VERSION,
    presets: base.presets.filter(
      (preset) => preset.name.toLowerCase() !== key,
    ),
  };
}
