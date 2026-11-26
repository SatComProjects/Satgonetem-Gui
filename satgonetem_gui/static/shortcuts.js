/** Global keyboard shortcuts and the help dialog. */
import { byId } from "./dom.js";
import {
  hasShortcutModifier,
  isEditableTarget,
  resolveGoKey,
  shortcutRows,
} from "./shortcuts_model.js?v=1";

const PREFIX_TIMEOUT_MS = 900;

let goPending = false;
let goTimer = null;
let helpOpener = null;

function resultsOpen() {
  const modal = byId("results-modal");
  return Boolean(modal) && modal.style.display !== "none";
}

function helpDialog() {
  return byId("shortcuts-help");
}

function helpOpen() {
  const dialog = helpDialog();
  return Boolean(dialog?.open);
}

function clearGoPrefix() {
  goPending = false;
  if (goTimer !== null) {
    clearTimeout(goTimer);
    goTimer = null;
  }
}

function fillShortcutList() {
  const list = byId("shortcuts-list");
  if (!list || list.childElementCount) return;
  for (const row of shortcutRows()) {
    const item = document.createElement("li");
    item.className = "shortcuts-row";
    const keys = document.createElement("kbd");
    keys.textContent = row.keys;
    const label = document.createElement("span");
    label.textContent = row.label;
    item.append(keys, label);
    list.appendChild(item);
  }
}

function openHelp() {
  const dialog = helpDialog();
  if (!dialog || dialog.open) return;
  fillShortcutList();
  helpOpener = document.activeElement;
  if (typeof dialog.showModal === "function") dialog.showModal();
  else dialog.setAttribute("open", "");
  byId("shortcuts-close")?.focus();
}

function closeHelp() {
  const dialog = helpDialog();
  if (!dialog) return;
  if (typeof dialog.close === "function") dialog.close();
  else dialog.removeAttribute("open");
  if (helpOpener && typeof helpOpener.focus === "function") {
    helpOpener.focus();
  }
  helpOpener = null;
}

function navigate(path) {
  if (window.location.pathname === path) return;
  window.location.assign(path);
}

function handleKeydown(event) {
  if (hasShortcutModifier(event) || event.repeat) return;
  const editable = isEditableTarget(event.target);

  if (event.key === "Escape") {
    if (helpOpen()) {
      event.preventDefault();
      closeHelp();
    }
    return;
  }

  if (editable) return;
  if (helpOpen()) return;
  if (resultsOpen()) return;

  if (event.key === "?") {
    event.preventDefault();
    openHelp();
    return;
  }

  if (goPending) {
    const target = resolveGoKey(event.key);
    clearGoPrefix();
    if (target) {
      event.preventDefault();
      navigate(target.path);
    }
    return;
  }

  if (event.key.toLowerCase() === "g") {
    event.preventDefault();
    goPending = true;
    goTimer = setTimeout(clearGoPrefix, PREFIX_TIMEOUT_MS);
  }
}

function initialize() {
  document.addEventListener("keydown", handleKeydown);
  byId("shortcuts-help-btn")?.addEventListener("click", openHelp);
  byId("shortcuts-close")?.addEventListener("click", closeHelp);
  const dialog = helpDialog();
  dialog?.addEventListener("close", () => {
    if (helpOpener && typeof helpOpener.focus === "function") {
      helpOpener.focus();
    }
    helpOpener = null;
  });
  dialog?.addEventListener("click", (event) => {
    if (event.target === dialog) closeHelp();
  });
  document.documentElement.dataset.shortcuts = "ready";
}

initialize();
