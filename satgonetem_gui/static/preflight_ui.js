/**
 * Shared preflight rendering for the Dashboard and New Project pages.
 */
import { api } from "./api.js?v=4";
import { setStatus } from "./dom.js";
import { escapeHtml } from "./escape.js";
import {
  formatEstimate,
  hasBlockingCheck,
  preflightSummary,
} from "./preflight_model.js?v=1";

/**
 * @param {object|null} [payload]
 * @returns {Promise<object>}
 */
export function fetchPreflight(payload = undefined) {
  return api.post("/api/diagnostics/preflight", payload, { timeout: 15000 });
}

function dotClass(status) {
  if (status === "ok") return "ok";
  if (status === "error") return "bad";
  return "";
}

/**
 * @param {object} data
 * @param {HTMLElement|null|undefined} element
 */
function renderChecks(data, element) {
  if (!element) return;
  const checks = Array.isArray(data?.checks) ? data.checks : [];
  if (!checks.length) {
    element.innerHTML = '<p class="muted">No readiness checks were returned.</p>';
    return;
  }
  element.innerHTML = checks
    .map((check) => {
      const hint = check.hint
        ? `<p class="preflight-hint">${escapeHtml(check.hint)}</p>`
        : "";
      return `
        <div class="preflight-check" data-status="${escapeHtml(check.status)}">
          <span class="status-dot ${dotClass(check.status)}"></span>
          <div class="preflight-check-body">
            <strong>${escapeHtml(check.label)}</strong>
            <p class="preflight-check-message">${escapeHtml(check.message)}</p>
            ${hint}
          </div>
        </div>`;
    })
    .join("");
}

/**
 * @param {object|null|undefined} estimate
 * @param {HTMLElement|null|undefined} element
 */
function renderEstimate(estimate, element) {
  if (!element) return;
  if (!estimate) {
    element.replaceChildren();
    return;
  }
  const warnings = Array.isArray(estimate.warnings) ? estimate.warnings : [];
  element.innerHTML =
    `<div class="preflight-estimate-line">${escapeHtml(formatEstimate(estimate))}</div>` +
    (warnings.length
      ? '<ul class="preflight-warnings">' +
        warnings.map((warning) => `<li>${escapeHtml(warning)}</li>`).join("") +
        "</ul>"
      : "");
}

/**
 * @param {object} data
 * @param {{
 *   checksElement?: HTMLElement|null,
 *   msgElement?: HTMLElement|null,
 *   estimateElement?: HTMLElement|null,
 * }} targets
 */
export function renderPreflight(data, targets = {}) {
  setStatus(
    targets.msgElement,
    preflightSummary(data),
    hasBlockingCheck(data?.checks),
  );
  renderChecks(data, targets.checksElement);
  renderEstimate(data?.estimate, targets.estimateElement);
}

/**
 * @param {object} targets
 * @param {object|null} [payload]
 * @returns {Promise<object>}
 */
export async function runPreflight(targets, payload = undefined) {
  setStatus(targets.msgElement, "Checking...");
  const data = await fetchPreflight(payload);
  renderPreflight(data, targets);
  return data;
}
