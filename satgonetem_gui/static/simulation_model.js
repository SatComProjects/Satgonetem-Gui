/**
 * Pure helpers for the simulation transport controls.
 *
 * No DOM access here so the formatting and enable/disable rules stay testable
 * with Vitest.
 */

/**
 * @param {number|null|undefined} currentStep
 * @param {number|null|undefined} totalSteps
 * @returns {number} Integer percentage in [0, 100].
 */
export function progressPercent(currentStep, totalSteps) {
  const current = Number(currentStep);
  const total = Number(totalSteps);
  if (!Number.isFinite(current) || !Number.isFinite(total) || total <= 0) {
    return 0;
  }
  return Math.max(0, Math.min(100, Math.round((current / total) * 100)));
}

/**
 * @param {number|null|undefined} rate - Playback rate where higher is faster.
 * @returns {string}
 */
export function formatSimRate(rate) {
  const value = Number(rate);
  if (!Number.isFinite(value) || value <= 0) return "-";
  return `${Math.round(value * 100) / 100}\u00d7`;
}

/**
 * @param {string|null|undefined} value - ISO timestamp from the API.
 * @returns {string}
 */
export function formatSimTime(value) {
  if (!value) return "-";
  const text = String(value).replace("T", " ").replace(/\.\d+/, "");
  return text.endsWith("Z") ? `${text.slice(0, -1)} UTC` : text;
}

/**
 * @param {string|null|undefined} value - Last simulation tick error.
 * @returns {string}
 */
export function formatSimulationError(value) {
  return value ? `Last tick failed: ${value}` : "";
}

/**
 * Derive which transport actions are legal for a status snapshot.
 *
 * @param {Object|null|undefined} status
 * @returns {{
 *   loaded: boolean,
 *   running: boolean,
 *   startLabel: string,
 *   startDisabled: boolean,
 *   stepDisabled: boolean,
 *   resetDisabled: boolean,
 *   seekDisabled: boolean,
 *   speedDisabled: boolean,
 * }}
 */
export function simulationActionState(status) {
  const loaded = Boolean(status && status.constellation_loaded);
  const running = Boolean(status && status.simulation_updating);
  return {
    loaded,
    running,
    startLabel: running ? "Pause" : "Start",
    startDisabled: !loaded,
    stepDisabled: !loaded || running,
    resetDisabled: !loaded || running,
    seekDisabled: !loaded || running,
    speedDisabled: !loaded,
  };
}

/**
 * Validate a "go to step" value before sending it to the API.
 *
 * @param {string|number|null|undefined} value
 * @param {number|null|undefined} totalSteps
 * @returns {number|null} The step, or null when the input is invalid.
 */
export function normalizeSeekStep(value, totalSteps) {
  if (value === null || value === undefined || String(value).trim() === "") {
    return null;
  }
  const step = Number(value);
  const total = Number(totalSteps);
  if (!Number.isFinite(step) || !Number.isInteger(step)) return null;
  if (!Number.isFinite(total) || total < 0) return null;
  if (step < 0 || step > total) return null;
  return step;
}
