/**
 * Forwarding-path controls for the World View.
 *
 * Populates the source/destination selects, traces a path over the routing
 * graph snapshot, clears it, and reveals the link layers the path uses. The
 * page controller injects the render callbacks and visibility accessors so
 * this module never imports world.js.
 */

import { api } from "./api.js?v=4";
import { byId, setStatus } from "./dom.js";
import { pathLinkKeys, pathSummary } from "./path_model.js?v=1";

const LINK_CHECKBOXES = [
    ["cb-gsl", "gsl"],
    ["cb-orbital", "orbital"],
    ["cb-adjacent", "adjacent"],
];

/**
 * Build the path controller.
 *
 * @param {Object} deps
 * @param {Function} deps.rerenderLinks - Rebuild the Cesium link primitives.
 * @param {Function} deps.applyVisibility - Push the visibility state to Cesium.
 * @param {Function} deps.enableLinkVisibility - (key) => void, reveals a layer.
 * @param {Function} deps.isLinkVisible - (key) => boolean.
 * @returns {Object} Path state operations and control bindings.
 */
export function createWorldPath({
    rerenderLinks,
    applyVisibility,
    enableLinkVisibility,
    isLinkVisible,
}) {
    let pathKeys = new Set();
    let worldPathBusy = false;

    function setWorldPathMsg(text, isError = false) {
        setStatus(byId("world-path-msg"), text, isError);
    }

    function fillWorldPathSelect(select, nodes) {
        const previous = select.value;
        select.replaceChildren();
        for (const node of nodes) {
            const option = document.createElement("option");
            option.value = node.name;
            option.textContent =
                node.type === "ground_station" && node.city
                    ? `${node.name} (${node.city})`
                    : node.name;
            select.appendChild(option);
        }
        if (nodes.some((node) => node.name === previous)) {
            select.value = previous;
        }
    }

    async function loadWorldPathNodes() {
        const source = byId("world-path-src");
        const destination = byId("world-path-dst");
        const trace = byId("world-path-trace");
        const clear = byId("world-path-clear");
        if (!source || !destination) return;

        try {
            const nodes = await api.getAll("/api/nodes");
            const sorted = [...nodes].sort((a, b) =>
                a.name.localeCompare(b.name, undefined, { numeric: true }),
            );
            fillWorldPathSelect(source, sorted);
            fillWorldPathSelect(destination, sorted);
            if (!source.value && sorted.length) {
                const ground = sorted.find(
                    (node) => node.type === "ground_station",
                );
                source.value = (ground || sorted[0]).name;
            }
            if (!destination.value && sorted.length) {
                const satellite = sorted.find(
                    (node) => node.type === "satellite",
                );
                destination.value = (satellite || sorted[1] || sorted[0]).name;
            }
            const enabled = sorted.length >= 2;
            source.disabled = !enabled;
            destination.disabled = !enabled;
            if (trace) trace.disabled = worldPathBusy || !enabled;
            if (clear) clear.disabled = worldPathBusy || !enabled;
            if (!enabled) {
                setWorldPathMsg(
                    "Load a project with at least two nodes to trace a path.",
                );
            }
        } catch {
            source.disabled = true;
            destination.disabled = true;
            if (trace) trace.disabled = true;
            if (clear) clear.disabled = true;
            setWorldPathMsg("Load a project to trace a path.");
        }
    }

    function ensurePathLinkVisibility(hops) {
        for (const hop of hops || []) {
            if (hop.type === "GroundStationLink") {
                enableLinkVisibility("gsl");
            } else if (hop.type === "InterSatelliteLink") {
                const direction = String(hop.direction || "").toUpperCase();
                if (direction === "ORBITAL") {
                    enableLinkVisibility("orbital");
                } else if (direction === "ADJACENT") {
                    enableLinkVisibility("adjacent");
                } else {
                    enableLinkVisibility("orbital");
                    enableLinkVisibility("adjacent");
                }
            }
        }
        for (const [id, key] of LINK_CHECKBOXES) {
            const checkbox = byId(id);
            if (checkbox) checkbox.checked = isLinkVisible(key);
        }
        applyVisibility();
    }

    async function traceWorldPath() {
        if (worldPathBusy) return;
        const source = byId("world-path-src");
        const destination = byId("world-path-dst");
        const trace = byId("world-path-trace");
        const clear = byId("world-path-clear");
        const summary = byId("world-path-summary");
        if (!source || !destination || !source.value || !destination.value) {
            setWorldPathMsg("Choose a source and destination.", true);
            return;
        }
        if (source.value === destination.value) {
            setWorldPathMsg("Choose two different nodes.", true);
            return;
        }

        worldPathBusy = true;
        if (trace) trace.disabled = true;
        if (clear) clear.disabled = true;
        if (summary) summary.textContent = "";
        setWorldPathMsg("Tracing path...");

        try {
            const data = await api.get(
                `/api/routing/path?src=${encodeURIComponent(source.value)}&dst=${encodeURIComponent(destination.value)}`,
            );
            pathKeys = data.found ? pathLinkKeys(data.hops) : new Set();
            if (summary) summary.textContent = pathSummary(data);
            if (data.found) {
                ensurePathLinkVisibility(data.hops);
                setWorldPathMsg(data.note || "");
            } else {
                setWorldPathMsg(data.note || "No path found.");
            }
        } catch (error) {
            pathKeys = new Set();
            if (summary) summary.textContent = "";
            setWorldPathMsg(
                error.message || "Could not trace the path.",
                true,
            );
        } finally {
            worldPathBusy = false;
            const enabled = (source?.options.length || 0) >= 2;
            if (trace) trace.disabled = !enabled;
            if (clear) clear.disabled = !enabled;
            rerenderLinks();
        }
    }

    function clearWorldPath() {
        pathKeys = new Set();
        const summary = byId("world-path-summary");
        if (summary) summary.textContent = "";
        setWorldPathMsg("");
        rerenderLinks();
    }

    /** Wire the trace and clear buttons. */
    function bindControls() {
        byId("world-path-trace")?.addEventListener("click", traceWorldPath);
        byId("world-path-clear")?.addEventListener("click", clearWorldPath);
    }

    return {
        fillWorldPathSelect,
        loadWorldPathNodes,
        ensurePathLinkVisibility,
        traceWorldPath,
        clearWorldPath,
        bindControls,
        hasPath: () => pathKeys.size > 0,
        isOnPath: (key) => pathKeys.has(key),
    };
}
