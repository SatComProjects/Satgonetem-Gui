/**
 * Link-usage colouring for the World View.
 *
 * Polls `/api/links/usage` while the "Color links by usage" checkbox is on and
 * keeps the latest utilization map. The page controller injects the rerender
 * callback and the DOM ids so this module never imports world.js.
 */

import { api } from "./api.js?v=4";
import { byId, setStatus } from "./dom.js";
import { linkKey } from "./path_model.js?v=1";

const USAGE_POLL_MS = 5000;

/**
 * Build the link-usage controller.
 *
 * @param {Object} deps
 * @param {Function} deps.rerenderLinks - Rebuild the Cesium link primitives.
 * @param {string} [deps.messageId] - Status element id for usage messages.
 * @param {string} [deps.checkboxId] - Checkbox id that toggles usage colouring.
 * @returns {Object} Polling lifecycle and usage-state accessors.
 */
export function createWorldUsage({
    rerenderLinks,
    messageId = "world-usage-msg",
    checkboxId = "cb-link-usage",
}) {
    let usageEnabled = false;
    let usageAvailable = false;
    let usageByLink = new Map();
    let usageTimer = null;
    let usageInFlight = false;

    function setUsageMessage(text, isError = false) {
        setStatus(byId(messageId), text, isError);
    }

    async function refreshUsage() {
        if (!usageEnabled || usageInFlight) return;
        usageInFlight = true;
        try {
            const data = await api.get("/api/links/usage");
            if (!usageEnabled) return;
            usageAvailable = Boolean(data.available);
            usageByLink = new Map(
                (Array.isArray(data.links) ? data.links : [])
                    .filter((entry) => entry && entry.src && entry.dst)
                    .map((entry) => [
                        linkKey(entry.src, entry.dst),
                        entry.utilization,
                    ]),
            );
            setUsageMessage(
                data.available ? "" : (data.note || "Link usage is unavailable."),
            );
        } catch (error) {
            usageAvailable = false;
            usageByLink.clear();
            setUsageMessage(
                "Link usage refresh failed: " + (error.message || "network error"),
                true,
            );
        } finally {
            usageInFlight = false;
        }
        rerenderLinks();
    }

    function setUsageEnabled(enabled) {
        usageEnabled = Boolean(enabled);
        if (usageTimer !== null) {
            clearInterval(usageTimer);
            usageTimer = null;
        }
        if (usageEnabled) {
            refreshUsage();
            usageTimer = setInterval(refreshUsage, USAGE_POLL_MS);
        } else {
            usageByLink.clear();
            usageAvailable = false;
            setUsageMessage("");
            rerenderLinks();
        }
    }

    /** Wire the link-usage checkbox. */
    function bindControl() {
        const checkbox = byId(checkboxId);
        if (!checkbox) return;
        checkbox.addEventListener("change", () =>
            setUsageEnabled(checkbox.checked),
        );
    }

    /** Stop the usage poll interval (page teardown). */
    function stopUsagePolling() {
        if (usageTimer !== null) {
            clearInterval(usageTimer);
            usageTimer = null;
        }
    }

    return {
        setEnabled: setUsageEnabled,
        bindControl,
        stopUsagePolling,
        isEnabled: () => usageEnabled,
        isAvailable: () => usageAvailable,
        utilizationFor: (key) => (usageByLink.has(key) ? usageByLink.get(key) : 0),
    };
}
