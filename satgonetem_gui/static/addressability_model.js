/**
 * Pure helpers for the satellite addressability controls.
 *
 * Addressability is session-scoped: core does not serialize the flag, so the
 * UI must make the current state and the routing-refresh requirement explicit.
 */

/**
 * @param {number|null|undefined} count
 * @param {number|null|undefined} total
 * @returns {string}
 */
export function addressabilitySummary(count, total) {
  const current = Number(count);
  const all = Number(total);
  if (!Number.isFinite(all) || all <= 0) {
    return "No satellites available";
  }
  if (!Number.isFinite(current) || current <= 0) {
    return `No satellites addressable (0 of ${all})`;
  }
  if (current >= all) {
    return `All ${all} satellites addressable`;
  }
  return `${current} of ${all} satellites addressable`;
}

/**
 * @param {number|null|undefined} count
 * @param {number|null|undefined} total
 * @returns {{checked: boolean, indeterminate: boolean, disabled: boolean}}
 */
export function addressabilityCheckboxState(count, total) {
  const current = Number(count);
  const all = Number(total);
  if (!Number.isFinite(all) || all <= 0) {
    return { checked: false, indeterminate: false, disabled: true };
  }
  return {
    checked: Number.isFinite(current) && current > 0,
    indeterminate:
      Number.isFinite(current) && current > 0 && current < all,
    disabled: false,
  };
}

/**
 * @param {boolean} required
 * @returns {string}
 */
export function routingRefreshMessage(required) {
  return required
    ? "Satellite endpoints updated. Re-apply Addressing & Routing on the Dashboard before running traffic."
    : "Satellite endpoints updated.";
}
