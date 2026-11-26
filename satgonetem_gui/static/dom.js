/**
 * Canonical DOM helpers shared by the page controllers.
 *
 * This module imports nothing so every page can load the same instance without
 * creating import cycles between controllers and models.
 */

/**
 * Look up an element by id.
 *
 * @param {string} id - Element id.
 * @returns {HTMLElement|null}
 */
export function byId(id) {
  return document.getElementById(id);
}

/**
 * Set a status/message element's text and error state.
 *
 * Empty text clears the error state so a stale failure colour never lingers.
 *
 * @param {HTMLElement|null|undefined} element - Target element.
 * @param {string} text - Message text.
 * @param {boolean} [isError] - Whether the message reports a failure.
 */
export function setStatus(element, text, isError = false) {
  if (!element) return;
  element.textContent = text;
  element.classList.toggle("is-error", Boolean(text) && isError);
}

/**
 * Download text as a file through a temporary object URL and anchor.
 *
 * @param {string} filename - Filename suggested to the browser.
 * @param {string} content - File content.
 * @param {string} [contentType] - MIME type for the generated Blob.
 */
export function downloadBlob(filename, content, contentType = "text/plain") {
  const blob = new Blob([content], { type: contentType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.style.display = "none";
  document.body.appendChild(anchor);
  try {
    anchor.click();
  } finally {
    URL.revokeObjectURL(url);
    anchor.remove();
  }
}
