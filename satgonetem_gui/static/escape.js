/** HTML-escape a value for text or quoted-attribute contexts. */
export function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  const replacements = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  };
  return String(value).replace(/[&<>"']/g, (character) => replacements[character]);
}
