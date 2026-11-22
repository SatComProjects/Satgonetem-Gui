/** Pure helpers for the new-project form. */

export function normalizeProjectName(value) {
  return String(value ?? "").trim();
}
