/**
 * Results/history dialog lifecycle.
 *
 * This module owns the shared `#results-modal` shell: opening and closing it,
 * the keyboard focus trap, restoring focus, making the rest of the page inert,
 * and Escape handling. Views register themselves as the active owner so the
 * dialog body events are only routed to the view that is currently rendered.
 */
import { byId } from "./dom.js";

const owners = new Map();
const modalBackground = [];
let modalOwner = null;
let lastFocused = null;
let destroyChartsHook = () => {};
let fallbackFocus = () => {};
let initialized = false;

function setModalBackgroundInert(inert) {
  if (inert) {
    modalBackground.length = 0;
    for (const child of document.body.children) {
      if (child.id === "results-modal" || child.tagName === "SCRIPT") continue;
      if (!child.inert) {
        child.inert = true;
        modalBackground.push(child);
      }
    }
    return;
  }
  for (const child of modalBackground.splice(0)) {
    child.inert = false;
  }
}

function activeHandlers() {
  return (modalOwner && owners.get(modalOwner)) || {};
}

function handleBodyClick(event) {
  const handler = activeHandlers().onBodyClick;
  if (handler) handler(event);
}

function handleBodyChange(event) {
  const handler = activeHandlers().onBodyChange;
  if (handler) handler(event);
}

function handleKeydown(event) {
  const modal = byId("results-modal");
  if (!modal || modal.style.display === "none") return;
  if (event.key === "Escape") {
    closeResults();
    return;
  }
  if (event.key !== "Tab") return;
  const focusable = Array.from(
    modal.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((element) => !element.disabled);
  if (focusable.length === 0) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

/**
 * Register the modal body handlers for one view.
 *
 * @param {string} name - Owner name passed to {@link openModal}.
 * @param {{
 *   onBodyClick?: (event: MouseEvent) => void,
 *   onBodyChange?: (event: Event) => void,
 * }} handlers
 */
export function registerModalOwner(name, handlers) {
  if (!name) return;
  owners.set(name, handlers || {});
}

/**
 * Name of the view that currently owns the modal contents, or null when the
 * modal is closed or shows a view without body handlers (for example a plot).
 *
 * @returns {string|null}
 */
export function getModalOwner() {
  return modalOwner;
}

/**
 * Bind the dialog controls once per page.
 *
 * The chart lifecycle and queue focus fallback are injected by the queue
 * controller so this module never imports the plotting or queue modules.
 *
 * @param {{
 *   destroyCharts?: () => void,
 *   fallbackFocus?: () => void,
 * }} hooks
 */
export function initResultsModal(hooks = {}) {
  if (typeof hooks.destroyCharts === "function") {
    destroyChartsHook = hooks.destroyCharts;
  }
  if (typeof hooks.fallbackFocus === "function") {
    fallbackFocus = hooks.fallbackFocus;
  }
  if (initialized) return;
  initialized = true;
  byId("results-close")?.addEventListener("click", closeResults);
  byId("results-backdrop")?.addEventListener("click", closeResults);
  byId("results-body")?.addEventListener("click", handleBodyClick);
  byId("results-body")?.addEventListener("change", handleBodyChange);
  document.addEventListener("keydown", handleKeydown);
}

/**
 * Open the dialog with the supplied markup and owner.
 *
 * @param {string} title
 * @param {string} body - Trusted markup assembled by the owning view.
 * @param {string|null} [owner] - Registered owner name for body events.
 */
export function openModal(title, body, owner = null) {
  const modal = byId("results-modal");
  const titleElement = byId("results-title");
  const bodyElement = byId("results-body");
  modalOwner = owner;
  destroyChartsHook();
  if (titleElement) titleElement.textContent = title;
  if (bodyElement) bodyElement.innerHTML = body;
  if (modal) {
    lastFocused = document.activeElement;
    modal.style.display = "flex";
    setModalBackgroundInert(true);
    byId("results-close")?.focus();
  }
}

/** Close the dialog, destroy live charts, and restore focus. */
export function closeResults() {
  const modal = byId("results-modal");
  if (modal) modal.style.display = "none";
  modalOwner = null;
  setModalBackgroundInert(false);
  destroyChartsHook();
  if (
    lastFocused &&
    lastFocused.isConnected &&
    typeof lastFocused.focus === "function"
  ) {
    lastFocused.focus();
  } else {
    fallbackFocus();
  }
  lastFocused = null;
}
