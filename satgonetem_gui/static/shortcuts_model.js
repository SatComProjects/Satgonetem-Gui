/** Pure keyboard shortcut metadata and guards. */

export const GO_TARGETS = {
  d: { path: "/", label: "Dashboard" },
  w: { path: "/world", label: "World View" },
  n: { path: "/nodes", label: "Nodes" },
  t: { path: "/traffic", label: "Traffic" },
};

export const SHORTCUTS = [
  { keys: "?", label: "Open keyboard shortcuts" },
  { keys: "g d", label: "Go to Dashboard" },
  { keys: "g w", label: "Go to World View" },
  { keys: "g n", label: "Go to Nodes" },
  { keys: "g t", label: "Go to Traffic" },
  { keys: "Esc", label: "Close the shortcuts or results dialog" },
];

const EDITABLE_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT"]);

export function isEditableTarget(target) {
  if (!target) return false;
  const tag = String(target.tagName || "").toUpperCase();
  return EDITABLE_TAGS.has(tag) || target.isContentEditable === true;
}

export function hasShortcutModifier(event) {
  return Boolean(event?.ctrlKey || event?.metaKey || event?.altKey);
}

export function resolveGoKey(key) {
  return GO_TARGETS[String(key ?? "").toLowerCase()] || null;
}

export function shortcutRows() {
  return SHORTCUTS.map((shortcut) => ({
    keys: shortcut.keys,
    label: shortcut.label,
  }));
}
