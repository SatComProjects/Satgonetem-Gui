/**
 * Shared status, artifact, and chart helpers for the experiment page.
 *
 * The list, detail, and comparison controllers render the same artifact
 * buttons and line-chart chrome. Keeping those primitives here avoids
 * importing one panel controller into the other (which would create an import
 * cycle between `experiments_detail.js` and `experiments_compare.js`).
 */
import { byId, setStatus } from "./dom.js";
import { escapeHtml } from "./escape.js";
import { artifactLabel } from "./experiments_model.js?v=2";

const GRID_COLOR = "rgba(138, 160, 183, 0.15)";

/**
 * Set the page-level experiments message region.
 *
 * @param {string} text - Message text.
 * @param {boolean} [isError] - Whether the message reports a failure.
 */
export function setPageMessage(text, isError = false) {
  setStatus(byId("experiments-msg"), text, isError);
}

/**
 * Set one panel's chart message region.
 *
 * @param {string} id - Chart message element id.
 * @param {string} text - Message text.
 * @param {boolean} [isError] - Whether the message reports a failure.
 */
export function setChartMessage(id, text, isError = false) {
  setStatus(byId(id), text, isError);
}

/**
 * Build the artifact download buttons for one run.
 *
 * Shared by the run list rows and the detail panel so both emit identical
 * markup and labels.
 *
 * @param {object} run - Run record.
 * @returns {string} HTML for the buttons, empty when the run has no artifacts.
 */
export function artifactButtons(run) {
  const artifacts = Array.isArray(run.artifacts) ? run.artifacts : [];
  if (!artifacts.length) return "";
  const id = escapeHtml(run.run_id);
  return artifacts
    .map(
      (name) =>
        `<button type="button" class="button small secondary" data-run-id="${id}" data-artifact="${escapeHtml(name)}">${escapeHtml(artifactLabel(name))}</button>`,
    )
    .join("");
}

/**
 * Destroy a Chart.js instance, tolerating an already-detached chart.
 *
 * @param {object|null} chart - Chart instance.
 * @returns {null} Always null so callers can assign the reset value.
 */
export function destroyChart(chart) {
  if (!chart) return null;
  try {
    chart.destroy();
  } catch {
    /* a detached chart is harmless */
  }
  return null;
}

/**
 * Read a CSS custom property, falling back when it is not defined.
 *
 * @param {string} name - Custom property name, e.g. `--accent`.
 * @param {string} fallback - Colour used when the property is empty.
 * @returns {string}
 */
export function cssColor(name, fallback) {
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value || fallback;
}

/**
 * Create the shared line-chart shell used by the detail and comparison panels.
 *
 * The caller checks for Chart.js availability and builds the datasets; the
 * axes, legend, and interaction options live here so both charts stay
 * consistent.
 *
 * @param {HTMLCanvasElement} canvas - Target canvas.
 * @param {{datasets: object[], yTitle: string, yTick: (value: number) => string, beginAtZero?: boolean}} config
 * @returns {object} The created Chart.js instance.
 */
export function createLineChart(
  canvas,
  { datasets, yTitle, yTick, beginAtZero = true },
) {
  const text = cssColor("--muted", "#8aa0b7");
  return new window.Chart(canvas, {
    type: "line",
    data: { datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      parsing: false,
      interaction: { mode: "nearest", intersect: false },
      plugins: {
        legend: { labels: { color: text } },
      },
      scales: {
        x: {
          type: "linear",
          title: { display: true, text: "Simulation time (s)", color: text },
          ticks: { color: text },
          grid: { color: GRID_COLOR },
        },
        y: {
          beginAtZero,
          title: { display: true, text: yTitle, color: text },
          ticks: { color: text, callback: yTick },
          grid: { color: GRID_COLOR },
        },
      },
    },
  });
}
