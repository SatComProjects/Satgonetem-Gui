/** Pure formatting helpers for the project workspace page. */

/**
 * @param {number|null|undefined} bytes
 * @returns {string}
 */
export function formatProjectSize(bytes) {
  if (bytes === null || bytes === undefined || bytes === "") return "\u2014";
  const value = Number(bytes);
  if (!Number.isFinite(value) || value < 0) return "\u2014";
  if (value >= 1024 ** 3) return `${Number((value / 1024 ** 3).toFixed(2))} GB`;
  if (value >= 1024 ** 2) return `${Number((value / 1024 ** 2).toFixed(2))} MB`;
  if (value >= 1024) return `${Number((value / 1024).toFixed(1))} KB`;
  return `${value} B`;
}

/**
 * @param {string|null|undefined} iso
 * @returns {string}
 */
export function formatProjectDate(iso) {
  if (!iso) return "\u2014";
  return String(iso)
    .replace("T", " ")
    .replace(/\.\d+/, "")
    .replace(/Z$/, " UTC");
}

/**
 * @param {number|null|undefined} value
 * @returns {string}
 */
export function formatProjectCount(value) {
  if (value === null || value === undefined || value === "") return "\u2014";
  const number = Number(value);
  return Number.isInteger(number) && number >= 0 ? String(number) : "\u2014";
}

/**
 * @param {string|null|undefined} name
 * @returns {boolean}
 */
export function projectNameValid(name) {
  return typeof name === "string" && name.trim().length > 0;
}

