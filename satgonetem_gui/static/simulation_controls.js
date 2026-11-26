/**
 * Wire the simulation transport panel to the simulation API.
 *
 * The panel markup is shared by the dashboard and World View. Dashboard polls
 * /api/status for other cards, so it passes status snapshots via apply();
 * World View lets this module poll on its own.
 */
import { api } from "./api.js?v=4";
import { byId, setStatus } from "./dom.js";
import {
  formatSimRate,
  formatSimTime,
  formatSimulationError,
  normalizeSeekStep,
  progressPercent,
  simulationActionState,
} from "./simulation_model.js?v=1";

const POLL_INTERVAL_MS = 2000;
const CONTROL_TIMEOUT_MS = 600000;

/**
 * @param {Object} [options]
 * @param {boolean} [options.poll] - Poll /api/status from this module.
 * @returns {{apply: Function, refresh: Function, dispose: Function}}
 */
export function initSimulationControls({ poll = true } = {}) {
  const elements = {
    dot: byId("dot-running"),
    label: byId("label-running"),
    step: byId("val-step"),
    total: byId("val-total-steps"),
    time: byId("val-time"),
    rate: byId("val-sim-rate"),
    progress: byId("sim-progress"),
    progressBar: byId("sim-progress-bar"),
    start: byId("sim-start"),
    stepButton: byId("sim-step"),
    reset: byId("sim-reset"),
    slower: byId("sim-slower"),
    faster: byId("sim-faster"),
    seekForm: byId("sim-seek-form"),
    seekStep: byId("sim-seek-step"),
    seekSubmit: byId("sim-seek-submit"),
    message: byId("sim-msg"),
    error: byId("sim-error"),
  };

  if (!elements.start || !elements.progressBar) {
    return { apply() {}, refresh: async () => null, dispose() {} };
  }

  let lastStatus = null;
  let busy = false;
  let refreshing = false;
  let pollTimer = null;

  function setMessage(text, isError = false) {
    setStatus(elements.message, text, isError);
  }

  function updateControls() {
    const state = simulationActionState(lastStatus);
    const disabled = busy;
    elements.start.disabled = disabled || state.startDisabled;
    elements.start.textContent = busy ? "Working..." : state.startLabel;
    elements.stepButton.disabled = disabled || state.stepDisabled;
    elements.reset.disabled = disabled || state.resetDisabled;
    elements.slower.disabled = disabled || state.speedDisabled;
    elements.faster.disabled = disabled || state.speedDisabled;
    if (elements.seekStep) {
      elements.seekStep.disabled = disabled || state.seekDisabled;
      elements.seekStep.max =
        Number.isFinite(Number(lastStatus && lastStatus.total_steps))
          ? String(lastStatus.total_steps)
          : "";
    }
    if (elements.seekSubmit) {
      elements.seekSubmit.disabled = disabled || state.seekDisabled;
    }
  }

  function apply(status) {
    if (!status) return;
    lastStatus = status;
    const state = simulationActionState(status);

    if (elements.dot) {
      elements.dot.classList.toggle("ok", state.running);
      elements.dot.classList.toggle("bad", !state.running);
    }
    if (elements.label) {
      elements.label.textContent = state.running
        ? "Running"
        : state.loaded
          ? "Idle"
          : "Not loaded";
    }
    if (elements.step) {
      elements.step.textContent =
        status.current_step !== null && status.current_step !== undefined
          ? status.current_step
          : "-";
    }
    if (elements.total) {
      elements.total.textContent =
        status.total_steps !== null && status.total_steps !== undefined
          ? status.total_steps
          : "-";
    }
    if (elements.time) {
      elements.time.textContent = formatSimTime(status.current_time);
    }
    if (elements.rate) {
      elements.rate.textContent = formatSimRate(status.simulation_rate);
    }
    const percent = progressPercent(status.current_step, status.total_steps);
    if (elements.progress) {
      elements.progress.setAttribute("aria-valuenow", String(percent));
      elements.progress.setAttribute("aria-valuetext", `${percent}% complete`);
    }
    if (elements.progressBar) {
      elements.progressBar.style.width = `${percent}%`;
    }
    if (elements.error) {
      elements.error.textContent = formatSimulationError(
        status.last_simulation_error,
      );
    }
    updateControls();
  }

  async function refresh() {
    if (refreshing) return null;
    refreshing = true;
    try {
      const status = await api.get("/api/status");
      apply(status);
      return status;
    } catch (err) {
      setMessage(
        "Status refresh failed: " + (err.message || "network error"),
        true,
      );
      return null;
    } finally {
      refreshing = false;
    }
  }

  async function run(path, body, pendingText) {
    if (busy) return;
    busy = true;
    setMessage(pendingText);
    updateControls();
    try {
      await api.post(path, body, { timeout: CONTROL_TIMEOUT_MS });
      setMessage("");
      await refresh();
    } catch (err) {
      setMessage(err.message || "Simulation action failed.", true);
    } finally {
      busy = false;
      updateControls();
    }
  }

  elements.start.addEventListener("click", () => {
    const running = Boolean(lastStatus && lastStatus.simulation_updating);
    run(
      running ? "/api/simulation/stop" : "/api/simulation/start",
      undefined,
      running ? "Pausing simulation..." : "Starting simulation...",
    );
  });

  elements.stepButton.addEventListener("click", () => {
    run("/api/simulation/step", undefined, "Advancing one step...");
  });

  elements.reset.addEventListener("click", () => {
    run("/api/simulation/reset", undefined, "Resetting simulation...");
  });

  elements.faster.addEventListener("click", () => {
    run(
      "/api/simulation/speed",
      { direction: "faster" },
      "Increasing playback speed...",
    );
  });

  elements.slower.addEventListener("click", () => {
    run(
      "/api/simulation/speed",
      { direction: "slower" },
      "Decreasing playback speed...",
    );
  });

  if (elements.seekForm) {
    elements.seekForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const step = normalizeSeekStep(
        elements.seekStep.value,
        lastStatus && lastStatus.total_steps,
      );
      if (step === null) {
        setMessage("Enter a whole step within the project duration.", true);
        return;
      }
      run(
        "/api/simulation/seek",
        { step },
        `Seeking to step ${step}...`,
      );
    });
  }

  function dispose() {
    if (pollTimer !== null) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  if (poll) {
    refresh();
    pollTimer = setInterval(refresh, POLL_INTERVAL_MS);
    window.addEventListener("pagehide", dispose, { once: true });
  }

  return { apply, refresh, dispose };
}
