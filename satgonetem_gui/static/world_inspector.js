/**
 * DOM node inspector for the World View.
 *
 * Renders the selected satellite/ground-station panel, tracks the isolation
 * toggle, and caches the rendered signature so the two-second poll does not
 * rewrite unchanged DOM. Node and link data are injected lookups so this
 * module never imports world.js.
 */

import { byId } from "./dom.js";
import {
    formatCoordinate,
    nearestPeers,
    summarizeLinks,
} from "./world_model.js?v=3";

/**
 * Build the inspector controller.
 *
 * @param {Object} deps
 * @param {Cesium.Viewer} deps.viewer - Viewer queried for scene picks.
 * @param {Function} deps.getNodeInfo - (name) => node info or undefined.
 * @param {Function} deps.nodeInfoValues - Returns all node info records.
 * @param {Function} deps.getLinks - Returns the most recently rendered links.
 * @param {Function} deps.getSatelliteEntities - Returns name => satellite entity.
 * @param {Function} deps.getGroundStationEntities - Returns name => GS entity.
 * @param {Function} deps.resolveCoverageEntity - (entity) => satellite name|null.
 * @param {Function} deps.selectCoverageSatellite - (name|null) => void.
 * @param {Function} deps.rerenderLinks - Rebuild the Cesium link primitives.
 * @returns {Object} Selection, rendering, and control-binding operations.
 */
export function createWorldInspector({
    viewer,
    getNodeInfo,
    nodeInfoValues,
    getLinks,
    getSatelliteEntities,
    getGroundStationEntities,
    resolveCoverageEntity,
    selectCoverageSatellite,
    rerenderLinks,
}) {
    const inspector = { node: null, isolate: false, signature: "" };

    function fillInspectorList(element, rows) {
        if (!element) return;
        element.replaceChildren();
        for (const row of rows) {
            const item = document.createElement("li");
            item.textContent = row;
            element.appendChild(item);
        }
    }

    /**
     * Select one satellite or ground station and show the DOM inspector.
     * @param {string} name
     */
    function select(name) {
        const info = getNodeInfo(name);
        if (!info) {
            clear();
            return;
        }
        inspector.node = name;
        inspector.signature = "";
        selectCoverageSatellite(info.type === "satellite" ? name : null);
        render();
        rerenderLinks();
    }

    function clear() {
        inspector.node = null;
        inspector.signature = "";
        inspector.isolate = false;
        const isolate = byId("world-isolate-links");
        if (isolate) isolate.checked = false;
        selectCoverageSatellite(null);
        const panel = byId("world-inspector");
        if (panel) panel.hidden = true;
        rerenderLinks();
    }

    function render() {
        const name = inspector.node;
        const info = name ? getNodeInfo(name) : null;
        const panel = byId("world-inspector");
        if (!info || !panel) {
            if (panel) panel.hidden = true;
            return;
        }
        const lastLinks = getLinks();
        const summary = summarizeLinks(lastLinks, name);
        const peers = nearestPeers(info, [...nodeInfoValues()], 5);
        const neighborRows = summary.incident.map(
            (link) => `${link.peer} (${link.category})`,
        );
        const peerRows = peers.map(
            (peer) => `${peer.name} - ${peer.distance_km} km`,
        );
        const signature = [
            name,
            info.position?.latitude,
            info.position?.longitude,
            info.position?.altitude,
            lastLinks.length,
            neighborRows.join("|"),
            peerRows.join("|"),
        ].join("~");
        if (signature === inspector.signature) {
            panel.hidden = false;
            return;
        }
        inspector.signature = signature;

        const title = byId("world-inspector-title");
        if (title) title.textContent = name;
        const kind = byId("world-inspector-kind");
        if (kind) {
            kind.textContent =
                info.type === "ground_station"
                    ? `Ground station${info.city ? ` - ${info.city}` : ""}`
                    : "Satellite";
        }
        const lat = byId("world-inspector-lat");
        if (lat) lat.textContent = formatCoordinate(info.position?.latitude);
        const lon = byId("world-inspector-lon");
        if (lon) lon.textContent = formatCoordinate(info.position?.longitude);
        const alt = byId("world-inspector-alt");
        if (alt) {
            alt.textContent = `${formatCoordinate(info.position?.altitude, 0)} km`;
        }
        const links = byId("world-inspector-links");
        if (links) {
            links.textContent =
                `${summary.total} links - GSL ${summary.byCategory.gsl}, ` +
                `orbital ${summary.byCategory.orbital}, ` +
                `adjacent ${summary.byCategory.adjacent}`;
        }
        fillInspectorList(
            byId("world-inspector-neighbors"),
            neighborRows.length ? neighborRows : ["No incident links."],
        );
        fillInspectorList(
            byId("world-inspector-peers"),
            peerRows.length ? peerRows : ["No positioned peers."],
        );
        panel.hidden = false;
    }

    /**
     * Pick the node under the cursor on left click.
     * A satellite dot or its coverage circle selects the satellite (dimming
     * all other circles); clicking empty space clears the selection.
     *
     * @returns {Cesium.ScreenSpaceEventHandler} Handler for page teardown.
     */
    function bindPicking() {
        const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
        handler.setInputAction((click) => {
            const picked = viewer.scene.pick(click.position);
            let nodeName = null;
            if (Cesium.defined(picked) && Cesium.defined(picked.id)) {
                const entity = picked.id;
                const satellites = getSatelliteEntities();
                const groundStations = getGroundStationEntities();
                nodeName =
                    Object.keys(satellites).find(
                        (name) => satellites[name] === entity,
                    ) ||
                    Object.keys(groundStations).find(
                        (name) => groundStations[name] === entity,
                    ) ||
                    resolveCoverageEntity(entity) ||
                    null;
            }
            if (nodeName) select(nodeName);
            else clear();
        }, Cesium.ScreenSpaceEventType.LEFT_CLICK);
        return handler;
    }

    /** Wire the close button and the isolate-links checkbox. */
    function bindControls() {
        const isolate = byId("world-isolate-links");
        if (isolate) {
            isolate.checked = false;
            isolate.addEventListener("change", () => {
                inspector.isolate = isolate.checked;
                rerenderLinks();
            });
        }
        byId("world-inspector-close")?.addEventListener("click", clear);
    }

    /** Currently selected node name, or null. */
    function getSelectedNode() {
        return inspector.node;
    }

    /** True when the selected node exists in the current entity sync. */
    function hasNode(name) {
        return Boolean(getNodeInfo(name));
    }

    /**
     * Name of the node whose links are isolated, or null when isolation is off.
     * Link rendering skips every link that does not touch this node.
     */
    function getIsolationNode() {
        return inspector.isolate ? inspector.node : null;
    }

    return {
        select,
        clear,
        render,
        bindControls,
        bindPicking,
        getSelectedNode,
        hasNode,
        getIsolationNode,
    };
}
