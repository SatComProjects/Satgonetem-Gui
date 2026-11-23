import { describe, expect, it } from "vitest";

import {
  GO_TARGETS,
  hasShortcutModifier,
  isEditableTarget,
  resolveGoKey,
  shortcutRows,
} from "../satgonetem_gui/static/shortcuts_model.js";

describe("keyboard shortcut guards", () => {
  it("detects editable targets", () => {
    expect(isEditableTarget({ tagName: "INPUT" })).toBe(true);
    expect(isEditableTarget({ tagName: "textarea" })).toBe(true);
    expect(isEditableTarget({ tagName: "SELECT" })).toBe(true);
    expect(isEditableTarget({ tagName: "DIV", isContentEditable: true })).toBe(
      true,
    );
    expect(isEditableTarget({ tagName: "BUTTON" })).toBe(false);
    expect(isEditableTarget(null)).toBe(false);
  });

  it("ignores modified chords", () => {
    expect(hasShortcutModifier({ ctrlKey: true })).toBe(true);
    expect(hasShortcutModifier({ metaKey: true })).toBe(true);
    expect(hasShortcutModifier({ altKey: true })).toBe(true);
    expect(hasShortcutModifier({ shiftKey: true })).toBe(false);
    expect(hasShortcutModifier(null)).toBe(false);
  });

  it("resolves the g navigation targets", () => {
    expect(resolveGoKey("d").path).toBe("/");
    expect(resolveGoKey("W").path).toBe("/world");
    expect(resolveGoKey("n").path).toBe("/nodes");
    expect(resolveGoKey("t").path).toBe("/traffic");
    expect(resolveGoKey("x")).toBeNull();
    expect(resolveGoKey(null)).toBeNull();
    expect(Object.keys(GO_TARGETS)).toEqual(["d", "w", "n", "t"]);
  });

  it("exposes the shortcut catalogue", () => {
    const rows = shortcutRows();
    expect(rows.map((row) => row.keys)).toContain("?");
    expect(rows).toHaveLength(6);
    expect(rows.every((row) => row.label)).toBe(true);
  });
});
