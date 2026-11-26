import { api, ApiError } from "./api.js?v=4";
import { byId, setStatus } from "./dom.js";
import { initSimulationControls } from "./simulation_controls.js?v=2";
import { linkWidth, usageColor } from "./links_model.js?v=1";
import { linkKey } from "./path_model.js?v=1";
import { createWorldCoverage } from "./world_coverage.js?v=1";
import { createWorldInspector } from "./world_inspector.js?v=1";
import { createWorldPath } from "./world_path.js?v=1";
import { createWorldUsage } from "./world_usage.js?v=1";
import { deepLinkNode, describeGroundStation, describeSatellite, hasPosition, linkCategory } from "./world_model.js?v=3";

const SAT_COLOR = Cesium.Color.fromCssColorString("#3b82f6");
const GS_CONN_COLOR = Cesium.Color.fromCssColorString("#22c55e");
const GS_DISC_COLOR = Cesium.Color.fromCssColorString("#dc2626");
const LINK_COLORS = {
    gsl: Cesium.Color.fromCssColorString("#16a34a").withAlpha(0.75),
    orbital: Cesium.Color.fromCssColorString("#1e40af").withAlpha(0.75),
    adjacent: Cesium.Color.fromCssColorString("#dc2626").withAlpha(0.75),
};
const INACTIVE_LINK_COLOR = Cesium.Color.fromCssColorString("#ef4444");

let viewer = null;
const linkCollections = { gsl: null, orbital: null, adjacent: null };
const satEntities = {};
const gsEntities = {};
const nodePositions = new Map();
const nodeInfo = new Map();
const satPositions = {};
const vis = { satellites: true, groundStations: true, gsl: false, orbital: false, adjacent: false };

let coverage = null;
let inspector = null;
let worldPath = null;
let usage = null;

let lastLinks = [];
let pollTimer = null;
let clickHandler = null;
let worldDisposed = false;
let pendingDeepLink = deepLinkNode(window.location.search);

/** Convert geographic coordinates to a Cesium Cartesian3 position. */
function toCartesian(lat, lon, altKm) {
    return Cesium.Cartesian3.fromDegrees(lon, lat, (altKm || 0) * 1000);
}

/** Names of ground stations that have at least one GSL. */
function connectedGsNames(links) {
    const connected = new Set();
    links.forEach((lk) => {
        const t = (lk.type || "").toLowerCase();
        if (t.includes("groundstation") || t.includes("userterm")) {
            connected.add(lk.src);
            connected.add(lk.dst);
        }
    });
    return connected;
}

/** Initialise the Cesium viewer and the per-type polyline collections. */
function initCesium() {
    viewer = new Cesium.Viewer("world", {
        baseLayer: new Cesium.ImageryLayer(
            new Cesium.WebMapTileServiceImageryProvider({
                url: "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_NextGeneration/default/GoogleMapsCompatible_Level8/{TileMatrix}/{TileRow}/{TileCol}.jpg",
                layer: "BlueMarble_NextGeneration",
                style: "default",
                tileMatrixSetID: "GoogleMapsCompatible_Level8",
                maximumLevel: 8,
                credit: new Cesium.Credit("Imagery from NASA GIBS"),
            }),
        ),
        terrainProvider: new Cesium.EllipsoidTerrainProvider(),
        baseLayerPicker: false, geocoder: false, homeButton: false,
        navigationHelpButton: false, animation: false, timeline: false,
        sceneModePicker: false, infoBox: true, requestRenderMode: true,
        maximumRenderTimeChange: Infinity,
    });
    viewer.scene.globe.depthTestAgainstTerrain = true;

    Object.keys(linkCollections).forEach((key) => {
        const col = viewer.scene.primitives.add(new Cesium.PolylineCollection());
        col.show = vis[key];
        linkCollections[key] = col;
    });
}

/**
 * Sync satellite entities: create, move, and remove. Coverage circles are
 * maintained in parallel for every positioned satellite.
 */
function updateSatellites(satellites) {
    const seen = new Set();
    satellites.forEach((sat) => {
        const p = sat.position || {};
        if (!hasPosition(p)) {
            if (satEntities[sat.name]) {
                viewer.entities.remove(satEntities[sat.name]);
                delete satEntities[sat.name];
            }
            nodePositions.delete(sat.name);
            nodeInfo.delete(sat.name);
            delete satPositions[sat.name];
            coverage.removeSatellite(sat.name);
            return;
        }
        const pos = toCartesian(p.latitude, p.longitude, p.altitude);
        const description = describeSatellite(sat.name, p);
        nodePositions.set(sat.name, pos);
        nodeInfo.set(sat.name, { name: sat.name, type: "satellite", city: null, position: p });
        seen.add(sat.name);

        if (satEntities[sat.name]) {
            satEntities[sat.name].position = pos;
            satEntities[sat.name].show = vis.satellites;
            satEntities[sat.name].description = description;
        } else {
            satEntities[sat.name] = viewer.entities.add({
                name: sat.name,
                position: pos,
                point: { pixelSize: 5, color: SAT_COLOR },
                description,
                show: vis.satellites,
            });
        }

        satPositions[sat.name] = { latDeg: p.latitude, lonDeg: p.longitude, altKm: p.altitude };
        coverage.updateCoverageCircle(sat.name, p.latitude, p.longitude, p.altitude);
    });

    Object.keys(satEntities).forEach((name) => {
        if (!seen.has(name)) {
            viewer.entities.remove(satEntities[name]);
            delete satEntities[name];
            nodePositions.delete(name);
            nodeInfo.delete(name);
            delete satPositions[name];
            coverage.removeSatellite(name);
        }
    });
    coverage.retainSelection(seen);
}

/**
 * Sync ground station entities: green when linked, red when disconnected.
 * @param {Set<string>} connected - Names of stations with at least one link.
 */
function updateGroundStations(groundStations, connected) {
    const seen = new Set();
    groundStations.forEach((gs) => {
        const p = gs.position || {};
        if (!hasPosition(p)) {
            if (gsEntities[gs.name]) {
                viewer.entities.remove(gsEntities[gs.name]);
                delete gsEntities[gs.name];
            }
            nodePositions.delete(gs.name);
            nodeInfo.delete(gs.name);
            return;
        }
        const pos = toCartesian(p.latitude, p.longitude, p.altitude);
        const linked = connected.has(gs.name);
        const description = describeGroundStation(gs.name, gs.city, p, linked);
        nodePositions.set(gs.name, pos);
        nodeInfo.set(gs.name, {
            name: gs.name, type: "ground_station", city: gs.city || null, position: p,
        });
        seen.add(gs.name);

        if (gsEntities[gs.name]) {
            gsEntities[gs.name].position = pos;
            gsEntities[gs.name].point.color = linked ? GS_CONN_COLOR : GS_DISC_COLOR;
            gsEntities[gs.name].show = vis.groundStations;
            gsEntities[gs.name].description = description;
        } else {
            gsEntities[gs.name] = viewer.entities.add({
                name: gs.name,
                position: pos,
                point: {
                    pixelSize: 8,
                    color: linked ? GS_CONN_COLOR : GS_DISC_COLOR,
                    outlineColor: Cesium.Color.WHITE,
                    outlineWidth: 1,
                },
                label: {
                    text: gs.name,
                    font: "11px sans-serif",
                    fillColor: Cesium.Color.WHITE,
                    outlineColor: Cesium.Color.BLACK,
                    outlineWidth: 2,
                    style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                    pixelOffset: new Cesium.Cartesian2(0, -18),
                    show: true,
                },
                description,
                show: vis.groundStations,
            });
        }
    });

    Object.keys(gsEntities).forEach((name) => {
        if (!seen.has(name)) {
            viewer.entities.remove(gsEntities[name]);
            delete gsEntities[name];
            nodePositions.delete(name);
            nodeInfo.delete(name);
        }
    });
}

/** Rebuild every link polyline collection from the fetched links. */
function updateLinks(links) {
    lastLinks = Array.isArray(links) ? links : [];
    Object.values(linkCollections).forEach((col) => col.removeAll());

    const hasPath = worldPath.hasPath();
    const isolationNode = inspector.getIsolationNode();
    lastLinks.forEach((lk) => {
        const ltype = linkCategory(lk);
        const col = linkCollections[ltype];
        const src = nodePositions.get(lk.src);
        const dst = nodePositions.get(lk.dst);
        if (!src || !dst) return;

        const key = linkKey(lk.src, lk.dst);
        const onPath = hasPath && worldPath.isOnPath(key);
        const dim = hasPath && !onPath;
        const isolated =
            Boolean(isolationNode) && lk.src !== isolationNode && lk.dst !== isolationNode;
        const inactive = lk.is_active === false;
        let baseColor;
        if (inactive) {
            baseColor = INACTIVE_LINK_COLOR;
        } else if (usage.isEnabled()) {
            const ratio = usage.isAvailable() ? usage.utilizationFor(key) : null;
            baseColor = Cesium.Color.fromCssColorString(usageColor(ratio));
        } else {
            baseColor = LINK_COLORS[ltype];
        }
        const alpha = isolated ? 0.05 : dim ? 0.10 : onPath ? 1.0 : inactive ? 0.55 : 0.75;
        col.add({
            positions: [src, dst],
            width: inactive ? 1.0 : onPath ? 4.0 : linkWidth(lk.capacity_kbps),
            material: Cesium.Material.fromType("Color", {
                color: baseColor.withAlpha(alpha),
            }),
        });
    });

    viewer.scene.requestRender();
}

function showWorldMsg(text, isError = false) {
    setStatus(byId("world-msg"), text, isError);
}

/** Fetch satellites, ground stations, and links, then update the view. */
async function updateWorld() {
    try {
        const [satellites, groundStations, links] = await Promise.all([
            api.getAll("/api/satellites"),
            api.getAll("/api/ground_stations"),
            api.getAll("/api/links"),
        ]);

        if (!Array.isArray(satellites) || !Array.isArray(groundStations)) return;
        const linkArr = Array.isArray(links) ? links : [];
        const connected = connectedGsNames(linkArr);

        // Nodes must be updated before links so nodePositions is fresh.
        updateSatellites(satellites);
        updateGroundStations(groundStations, connected);
        updateLinks(linkArr);
        const selected = inspector.getSelectedNode();
        if (selected && !inspector.hasNode(selected)) {
            inspector.clear();
        } else if (selected) {
            inspector.render();
        }
        showWorldMsg(
            satellites.length || groundStations.length || linkArr.length ? "" : "No project data is available yet.",
        );
        if (pendingDeepLink) {
            const wanted = pendingDeepLink;
            pendingDeepLink = null;
            if (inspector.hasNode(wanted)) {
                inspector.select(wanted);
            } else {
                showWorldMsg(`Node not found: ${wanted}`, true);
            }
        }
    } catch (err) {
        console.error("World update error:", err);
        if (err instanceof ApiError && err.status === 404) {
            showWorldMsg("No project is loaded.");
        } else {
            showWorldMsg(`World view refresh failed: ${err.message || "network error"}`, true);
        }
    }
}

/** Propagate the current vis state to all entities and primitives. */
function applyVisibility() {
    Object.values(satEntities).forEach((e) => { e.show = vis.satellites; });
    Object.values(gsEntities).forEach((e) => { e.show = vis.groundStations; });
    linkCollections.gsl.show = vis.gsl;
    linkCollections.orbital.show = vis.orbital;
    linkCollections.adjacent.show = vis.adjacent;
    viewer.scene.requestRender();
}

/** Wire the node and link layer checkboxes to the visibility state. */
function bindVisibilityControls() {
    const cbMap = [
        ["cb-satellites", "satellites"],
        ["cb-ground-stations", "groundStations"],
        ["cb-gsl", "gsl"],
        ["cb-orbital", "orbital"],
        ["cb-adjacent", "adjacent"],
    ];
    cbMap.forEach(([id, key]) => {
        const el = byId(id);
        if (!el) return;
        el.checked = vis[key];
        el.addEventListener("change", () => {
            vis[key] = el.checked;
            applyVisibility();
        });
    });
}

/** Toggle the plot controls panel between collapsed and expanded. */
function togglePanel() {
    const panel = byId("plot-controls");
    const content = byId("plot-controls-content");
    const toggle = byId("plot-controls-toggle");
    const title = byId("plot-controls-title");
    const isNowCollapsed = panel.classList.toggle("collapsed");
    content.classList.toggle("collapsed", isNowCollapsed);
    toggle.textContent = isNowCollapsed ? "▶" : "◀";
    title.style.visibility = isNowCollapsed ? "hidden" : "visible";
    const header = byId("plot-controls-header");
    if (header) header.setAttribute("aria-expanded", String(!isNowCollapsed));
}

/** Rebuild the link primitives after selection/path/usage changes. */
function rerenderLinks() {
    if (lastLinks.length) updateLinks(lastLinks);
    else viewer?.scene.requestRender();
}

function cleanupWorld(event) {
    // A persisted pagehide freezes the page into the back/forward cache; the
    // view must stay usable when the browser restores it.
    if (event?.persisted || worldDisposed) return;
    worldDisposed = true;
    if (pollTimer !== null) {
        clearTimeout(pollTimer);
        pollTimer = null;
    }
    if (usage !== null) usage.stopUsagePolling();
    if (clickHandler !== null) {
        clickHandler.destroy();
        clickHandler = null;
    }
}

window.addEventListener("pagehide", cleanupWorld);

function poll() {
    updateWorld().finally(() => {
        if (!worldDisposed) pollTimer = setTimeout(poll, 2000);
    });
}

function startWorld() {
    initCesium();
    initSimulationControls({ poll: true });

    coverage = createWorldCoverage({
        viewer,
        requestRender: () => viewer.scene.requestRender(),
        getSatellitePositions: () => Object.entries(satPositions),
    });
    inspector = createWorldInspector({
        viewer,
        getNodeInfo: (name) => nodeInfo.get(name),
        nodeInfoValues: () => nodeInfo.values(),
        getLinks: () => lastLinks,
        getSatelliteEntities: () => satEntities,
        getGroundStationEntities: () => gsEntities,
        resolveCoverageEntity: (entity) => coverage.satelliteForEntity(entity),
        selectCoverageSatellite: (name) => coverage.selectSatellite(name),
        rerenderLinks,
    });
    worldPath = createWorldPath({
        rerenderLinks,
        applyVisibility,
        enableLinkVisibility: (key) => {
            vis[key] = true;
        },
        isLinkVisible: (key) => vis[key],
    });
    usage = createWorldUsage({
        rerenderLinks,
        messageId: "world-usage-msg",
        checkboxId: "cb-link-usage",
    });

    worldPath.bindControls();
    usage.bindControl();
    coverage.bindControls();
    inspector.bindControls();
    worldPath.loadWorldPathNodes();
    bindVisibilityControls();

    clickHandler = inspector.bindPicking();

    const panelHeader = byId("plot-controls-header");
    panelHeader.addEventListener("click", togglePanel);
    panelHeader.addEventListener("keydown", (event) => {
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        togglePanel();
    });

    poll();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", startWorld);
} else {
    startWorld();
}
