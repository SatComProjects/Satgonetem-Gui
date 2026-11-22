import { describe, expect, it } from "vitest";

import {
  MAX_PRESETS,
  findPreset,
  normalizePresetName,
  normalizePresets,
  presetFromFields,
  removePreset,
  upsertPreset,
} from "../satgonetem_gui/static/traffic_presets.js";

const fields = {
  tool: "ping",
  src: "Gnd0",
  dst: "Gnd1",
  delay: "0",
  pingCount: "5",
};

describe("traffic presets", () => {
  it("normalizes names and rejects incomplete presets", () => {
    expect(normalizePresetName("  Berlin   to Oslo  ")).toBe("Berlin to Oslo");
    expect(normalizePresetName(null)).toBe("");
    expect(presetFromFields("  Demo  ", fields)).toEqual({
      name: "Demo",
      fields,
    });
    expect(presetFromFields("", fields)).toBeNull();
    expect(presetFromFields("Demo", { ...fields, tool: "bogus" })).toBeNull();
    expect(presetFromFields("Demo", { ...fields, src: "" })).toBeNull();
    expect(presetFromFields("Demo", { ...fields, dst: "" })).toBeNull();
  });

  it("drops malformed and duplicate stored entries", () => {
    const presets = normalizePresets({
      version: 1,
      presets: [
        { name: "One", fields },
        { name: " one ", fields: { ...fields, src: "Other" } },
        { name: "", fields },
        { name: "Two", fields: { ...fields, tool: "bad" } },
        { name: "Three", fields: { ...fields, dst: "Gnd2" } },
        null,
      ],
    });

    expect(presets.version).toBe(1);
    expect(presets.presets.map((preset) => preset.name)).toEqual([
      "One",
      "Three",
    ]);
  });

  it("upserts case-insensitively and finds by name", () => {
    let collection = upsertPreset(null, { name: "Demo", fields });
    collection = upsertPreset(collection, {
      name: "demo",
      fields: { ...fields, src: "Gnd2" },
    });

    expect(collection.presets).toHaveLength(1);
    expect(collection.presets[0].name).toBe("demo");
    expect(collection.presets[0].fields.src).toBe("Gnd2");
    expect(findPreset(collection, "DEMO").name).toBe("demo");
    expect(findPreset(collection, "missing")).toBeNull();
    expect(findPreset(collection, "")).toBeNull();
  });

  it("caps the collection and removes presets", () => {
    let collection = null;
    for (let index = 0; index < MAX_PRESETS + 2; index += 1) {
      collection = upsertPreset(collection, {
        name: `Preset ${index}`,
        fields,
      });
    }

    expect(collection.presets).toHaveLength(MAX_PRESETS);
    expect(collection.presets[0].name).toBe("Preset 2");
    expect(collection.presets.at(-1).name).toBe(`Preset ${MAX_PRESETS + 1}`);

    collection = removePreset(collection, "preset 2");
    expect(collection.presets).toHaveLength(MAX_PRESETS - 1);
    expect(findPreset(collection, "Preset 2")).toBeNull();
  });
});
