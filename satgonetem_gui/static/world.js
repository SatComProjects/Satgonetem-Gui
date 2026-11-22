import { api, ApiError } from "./api.js?v=4";
import { initSimulationControls } from "./simulation_controls.js?v=1";
import { linkWidth, usageColor } from "./links_model.js?v=1";
import {
    linkKey,
    pathLinkKeys,
    pathSummary,
} from "./path_model.js?v=1";
import {
    describeGroundStation,
    describeSatellite,
    hasPosition,
    retainedSelection,
} from "./world_model.js?v=2";

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

const vis = {
    satellites: true,
    groundStations: true,
    gsl: false,
    orbital: false,
    adjacent: false,
};

const coverageEntities = {};

// Stores the most-recent lat/lon/alt for each satellite so coverage
// circles can be created immediately when the checkbox is toggled,
// without waiting for the next 2-second poll.
const satPositions = {};

const coverage = {
    enabled: false,
    elevationDeg: 10,
    opacity: 0.40,
    selectedSat: null,
};

let pathKeys = new Set();
let lastLinks = [];
let worldPathBusy = false;
let usageEnabled = false;
let usageAvailable = false;
let usageByLink = new Map();
let usageTimer = null;
let usageInFlight = false;

/**
 * Convert geographic coordinates to a Cesium Cartesian3 position.
 *
 * @param {number} lat - Latitude in degrees.
 * @param {number} lon - Longitude in degrees.
 * @param {number} altKm - Altitude in kilometres.
 * @returns {Cesium.Cartesian3}
 */
function toCartesian(lat, lon, altKm) {
    return Cesium.Cartesian3.fromDegrees(lon, lat, (altKm || 0) * 1000);
}

/**
 * Classify a link into one of the three display categories.
 *
 * @param {{type: string, direction: string}} link
 * @returns {"gsl"|"orbital"|"adjacent"}
 */
function classifyLink(link) {
    const t = (link.type || "").toLowerCase();
    if (t.includes("groundstation") || t.includes("userterm")) {
        return "gsl";
    }
    if ((link.direction || "").toUpperCase() === "ADJACENT") {
        return "adjacent";
    }
    return "orbital";
}

/**
 * Build the set of ground station names that have at least one active GSL.
 *
 * @param {Array} links
 * @returns {Set<string>}
 */
function connectedGsNames(links) {
    const connected = new Set();
    links.forEach(lk => {
        const t = (lk.type || "").toLowerCase();
        if (t.includes("groundstation") || t.includes("userterm")) {
            connected.add(lk.src);
            connected.add(lk.dst);
        }
    });
    return connected;
}

/**
 * Calculate the coverage circle radius on Earth's surface.
 *
 * Standard satellite geometry: in the triangle (Earth center, ground point,
 * satellite), the elevation angle at the ground point gives:
 *   sin(rho) = Re * cos(el) / (Re + h)
 *   lambda   = pi/2 - el - rho
 *   R        = Re * lambda
 *
 * @param {number} altKm - Satellite altitude in kilometres.
 * @param {number} elevationDeg - Minimum elevation angle in degrees.
 * @returns {number} Coverage radius in metres.
 */
function coverageRadiusMeters(altKm, elevationDeg) {
    const RE = 6371.0;
    const elRad = elevationDeg * Math.PI / 180;
    const sinRho = RE * Math.cos(elRad) / (RE + altKm);
    const rhoRad = Math.asin(Math.min(1, sinRho));
    const lambdaRad = Math.PI / 2 - elRad - rhoRad;
    return Math.max(0, RE * 1000 * lambdaRad);
}

/**
 * Return the effective fill opacity for a coverage circle.
 * When a satellite is selected, non-selected circles are dimmed to 15%.
 *
 * @param {string} satName
 * @returns {number} Opacity in [0, 1].
 */
function getEffectiveOpacity(satName) {
    if (coverage.selectedSat === null) return coverage.opacity;
    return satName === coverage.selectedSat ? coverage.opacity : coverage.opacity * 0.15;
}

/**
 * Create or update the coverage circle Cesium entity for a satellite.
 * The entity is always kept in sync with the satellite position; its
 * visibility is controlled separately via coverage.enabled.
 *
 * @param {string} satName
 * @param {number} latDeg
 * @param {number} lonDeg
 * @param {number} altKm
 */
function updateCoverageCircle(satName, latDeg, lonDeg, altKm) {
    const radius = coverageRadiusMeters(altKm, coverage.elevationDeg);
    const opacity = getEffectiveOpacity(satName);
    const groundPos = Cesium.Cartesian3.fromDegrees(lonDeg, latDeg, 0);

    if (coverageEntities[satName]) {
        const c = coverageEntities[satName];
        c.entity.position = groundPos;
        c.entity.ellipse.semiMajorAxis = radius;
        c.entity.ellipse.semiMinorAxis = radius;
        c.entity.ellipse.material = Cesium.Color.YELLOW.withAlpha(opacity);
        c.entity.show = coverage.enabled;
        c.altKm = altKm;
    } else {
        const entity = viewer.entities.add({
            position: groundPos,
            ellipse: {
                semiMajorAxis: radius,
                semiMinorAxis: radius,
                material: Cesium.Color.YELLOW.withAlpha(opacity),
                height: 0,
                outline: true,
                outlineColor: Cesium.Color.ORANGE.withAlpha(Math.min(1, opacity * 2)),
            },
            show: coverage.enabled,
        });
        coverageEntities[satName] = { entity, altKm };
    }
}

/**
 * Show or hide all coverage circle entities based on coverage.enabled.
 */
function applyCoverageVisibility() {
    Object.values(coverageEntities).forEach(c => {
        c.entity.show = coverage.enabled;
    });
    viewer.scene.requestRender();
}

/**
 * Recalculate and apply fill opacity for every coverage circle.
 * Called when the opacity slider changes or a satellite is selected/deselected.
 */
function applyCoverageOpacity() {
    Object.entries(coverageEntities).forEach(([name, c]) => {
        const op = getEffectiveOpacity(name);
        c.entity.ellipse.material = Cesium.Color.YELLOW.withAlpha(op);
        c.entity.ellipse.outlineColor = Cesium.Color.ORANGE.withAlpha(Math.min(1, op * 2));
    });
    viewer.scene.requestRender();
}

/**
 * Recalculate and apply coverage radii for all circles.
 * Called when the elevation slider changes.
 */
function applyCoverageElevation() {
    Object.entries(coverageEntities).forEach(([name, c]) => {
        const radius = coverageRadiusMeters(c.altKm, coverage.elevationDeg);
        c.entity.ellipse.semiMajorAxis = radius;
        c.entity.ellipse.semiMinorAxis = radius;
    });
    viewer.scene.requestRender();
}

/**
 * Initialise the Cesium viewer and the per-type polyline collections.
 */
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
            })
        ),
        terrainProvider: new Cesium.EllipsoidTerrainProvider(),
        baseLayerPicker: false,
        geocoder: false,
        homeButton: false,
        navigationHelpButton: false,
        animation: false,
        timeline: false,
        sceneModePicker: false,
        infoBox: true,
        requestRenderMode: true,
        maximumRenderTimeChange: Infinity,
    });

    viewer.scene.globe.depthTestAgainstTerrain = true;

    Object.keys(linkCollections).forEach(key => {
        const col = viewer.scene.primitives.add(new Cesium.PolylineCollection());
        col.show = vis[key];
        linkCollections[key] = col;
    });
}

/**
 * Sync satellite entities with the fetched data.
 * Creates new entities, updates positions of existing ones, removes stale ones.
 * Coverage circles are maintained in parallel for every satellite.
 *
 * @param {Array} satellites
 */
function updateSatellites(satellites) {
    const seen = new Set();
    satellites.forEach(sat => {
        const p = sat.position || {};
        if (!hasPosition(p)) {
            if (satEntities[sat.name]) {
                viewer.entities.remove(satEntities[sat.name]);
                delete satEntities[sat.name];
            }
            nodePositions.delete(sat.name);
            delete satPositions[sat.name];
            if (coverageEntities[sat.name]) {
                viewer.entities.remove(coverageEntities[sat.name].entity);
                delete coverageEntities[sat.name];
            }
            return;
        }
        const pos = toCartesian(p.latitude, p.longitude, p.altitude);
        nodePositions.set(sat.name, pos);
        seen.add(sat.name);

        if (satEntities[sat.name]) {
            satEntities[sat.name].position = pos;
            satEntities[sat.name].show = vis.satellites;
            satEntities[sat.name].description = describeSatellite(sat.name, p);
        } else {
            satEntities[sat.name] = viewer.entities.add({
                name: sat.name,
                position: pos,
                point: {
                    pixelSize: 5,
                    color: SAT_COLOR,
                },
                description: describeSatellite(sat.name, p),
                show: vis.satellites,
            });
        }

        satPositions[sat.name] = { latDeg: p.latitude, lonDeg: p.longitude, altKm: p.altitude };
        updateCoverageCircle(sat.name, p.latitude, p.longitude, p.altitude);
    });

    Object.keys(satEntities).forEach(name => {
        if (!seen.has(name)) {
            viewer.entities.remove(satEntities[name]);
            delete satEntities[name];
            nodePositions.delete(name);
            delete satPositions[name];

            if (coverageEntities[name]) {
                viewer.entities.remove(coverageEntities[name].entity);
                delete coverageEntities[name];
            }
        }
    });

    const retained = retainedSelection(coverage.selectedSat, seen);
    if (retained !== coverage.selectedSat) {
        coverage.selectedSat = retained;
        if (coverage.enabled) applyCoverageOpacity();
    }
}

/**
 * Sync ground station entities with the fetched data.
 * Color is green for connected stations and red for disconnected ones.
 *
 * @param {Array} groundStations
 * @param {Set<string>} connected - Names of stations with at least one active link.
 */
function updateGroundStations(groundStations, connected) {
    const seen = new Set();
    groundStations.forEach(gs => {
        const p = gs.position || {};
        if (!hasPosition(p)) {
            if (gsEntities[gs.name]) {
                viewer.entities.remove(gsEntities[gs.name]);
                delete gsEntities[gs.name];
            }
            nodePositions.delete(gs.name);
            return;
        }
        const pos = toCartesian(p.latitude, p.longitude, p.altitude);
        nodePositions.set(gs.name, pos);
        seen.add(gs.name);

        const color = connected.has(gs.name) ? GS_CONN_COLOR : GS_DISC_COLOR;

        if (gsEntities[gs.name]) {
            gsEntities[gs.name].position = pos;
            gsEntities[gs.name].point.color = color;
            gsEntities[gs.name].show = vis.groundStations;
            gsEntities[gs.name].description = describeGroundStation(
                gs.name,
                gs.city,
                p,
                connected.has(gs.name),
            );
        } else {
            gsEntities[gs.name] = viewer.entities.add({
                name: gs.name,
                position: pos,
                point: {
                    pixelSize: 8,
                    color: color,
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
                description: describeGroundStation(
                    gs.name,
                    gs.city,
                    p,
                    connected.has(gs.name),
                ),
                show: vis.groundStations,
            });
        }
    });

    Object.keys(gsEntities).forEach(name => {
        if (!seen.has(name)) {
            viewer.entities.remove(gsEntities[name]);
            delete gsEntities[name];
            nodePositions.delete(name);
        }
    });
}

/**
 * Rebuild the polyline primitives for all link types from the fetched links.
 * Clears each collection then re-populates it.
 *
 * @param {Array} links
 */
function updateLinks(links) {
    lastLinks = Array.isArray(links) ? links : [];
    Object.values(linkCollections).forEach(col => col.removeAll());

    const hasPath = pathKeys.size > 0;
    lastLinks.forEach(lk => {
        const ltype = classifyLink(lk);
        const col = linkCollections[ltype];
        const src = nodePositions.get(lk.src);
        const dst = nodePositions.get(lk.dst);
        if (!src || !dst) return;

        const key = linkKey(lk.src, lk.dst);
        const onPath = hasPath && pathKeys.has(key);
        const dim = hasPath && !onPath;
        const inactive = lk.is_active === false;
        let baseColor;
        if (inactive) {
            baseColor = INACTIVE_LINK_COLOR;
        } else if (usageEnabled) {
            const ratio = usageAvailable
                ? (usageByLink.has(key) ? usageByLink.get(key) : 0)
                : null;
            baseColor = Cesium.Color.fromCssColorString(usageColor(ratio));
        } else {
            baseColor = LINK_COLORS[ltype];
        }
        const alpha = dim ? 0.10 : onPath ? 1.0 : inactive ? 0.55 : 0.75;
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

/**
 * Fetch satellites, ground stations, and links from the API, then update the view.
 */
async function showWorldMsg(text, isError = false) {
    const element = document.getElementById("world-msg");
    if (!element) return;
    element.textContent = text;
    element.style.color = isError ? "var(--bad)" : "var(--muted)";
}

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

        // Satellites and ground stations must be updated before links
        // so nodePositions contains fresh positions when link endpoints are resolved.
        updateSatellites(satellites);
        updateGroundStations(groundStations, connected);
        updateLinks(linkArr);
        showWorldMsg(
            satellites.length || groundStations.length || linkArr.length
                ? ""
                : "No project data is available yet.",
        );
    } catch (err) {
        console.error("World update error:", err);
        if (err instanceof ApiError && err.status === 404) {
            showWorldMsg("No project is loaded.");
        } else {
            showWorldMsg(
                `World view refresh failed: ${err.message || "network error"}`,
                true,
            );
        }
    }
}

/**
 * Propagate the current vis state to all entities and primitives.
 */
function applyVisibility() {
    Object.values(satEntities).forEach(e => { e.show = vis.satellites; });
    Object.values(gsEntities).forEach(e => { e.show = vis.groundStations; });
    linkCollections.gsl.show = vis.gsl;
    linkCollections.orbital.show = vis.orbital;
    linkCollections.adjacent.show = vis.adjacent;
    viewer.scene.requestRender();
}

/**
 * Toggle the plot controls panel between collapsed and expanded.
 */
function togglePanel() {
    const panel = document.getElementById("plot-controls");
    const content = document.getElementById("plot-controls-content");
    const toggle = document.getElementById("plot-controls-toggle");
    const title = document.getElementById("plot-controls-title");
    const isNowCollapsed = panel.classList.toggle("collapsed");
    content.classList.toggle("collapsed", isNowCollapsed);
    toggle.textContent = isNowCollapsed ? "▶" : "◀";
    title.style.visibility = isNowCollapsed ? "hidden" : "visible";
    const header = document.getElementById("plot-controls-header");
    if (header) header.setAttribute("aria-expanded", String(!isNowCollapsed));
}

function setWorldPathMsg(text, isError = false) {
    const element = document.getElementById("world-path-msg");
    if (!element) return;
    element.textContent = text;
    element.style.color = isError ? "var(--bad)" : "var(--muted)";
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
    if (nodes.some(node => node.name === previous)) {
        select.value = previous;
    }
}

async function loadWorldPathNodes() {
    const source = document.getElementById("world-path-src");
    const destination = document.getElementById("world-path-dst");
    const trace = document.getElementById("world-path-trace");
    const clear = document.getElementById("world-path-clear");
    if (!source || !destination) return;

    try {
        const nodes = await api.getAll("/api/nodes");
        const sorted = [...nodes].sort((a, b) =>
            a.name.localeCompare(b.name, undefined, { numeric: true }),
        );
        fillWorldPathSelect(source, sorted);
        fillWorldPathSelect(destination, sorted);
        if (!source.value && sorted.length) {
            const ground = sorted.find(node => node.type === "ground_station");
            source.value = (ground || sorted[0]).name;
        }
        if (!destination.value && sorted.length) {
            const satellite = sorted.find(node => node.type === "satellite");
            destination.value = (satellite || sorted[1] || sorted[0]).name;
        }
        const enabled = sorted.length >= 2;
        source.disabled = !enabled;
        destination.disabled = !enabled;
        if (trace) trace.disabled = worldPathBusy || !enabled;
        if (clear) clear.disabled = worldPathBusy || !enabled;
        if (!enabled) {
            setWorldPathMsg("Load a project with at least two nodes to trace a path.");
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
            vis.gsl = true;
        } else if (hop.type === "InterSatelliteLink") {
            const direction = String(hop.direction || "").toUpperCase();
            if (direction === "ORBITAL") vis.orbital = true;
            else if (direction === "ADJACENT") vis.adjacent = true;
            else {
                vis.orbital = true;
                vis.adjacent = true;
            }
        }
    }
    const checkboxes = [
        ["cb-gsl", "gsl"],
        ["cb-orbital", "orbital"],
        ["cb-adjacent", "adjacent"],
    ];
    for (const [id, key] of checkboxes) {
        const checkbox = document.getElementById(id);
        if (checkbox) checkbox.checked = vis[key];
    }
    applyVisibility();
}

async function traceWorldPath() {
    if (worldPathBusy) return;
    const source = document.getElementById("world-path-src");
    const destination = document.getElementById("world-path-dst");
    const trace = document.getElementById("world-path-trace");
    const clear = document.getElementById("world-path-clear");
    const summary = document.getElementById("world-path-summary");
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
        setWorldPathMsg(error.message || "Could not trace the path.", true);
    } finally {
        worldPathBusy = false;
        const enabled = (source?.options.length || 0) >= 2;
        if (trace) trace.disabled = !enabled;
        if (clear) clear.disabled = !enabled;
        if (lastLinks.length) updateLinks(lastLinks);
        else viewer?.scene.requestRender();
    }
}

function clearWorldPath() {
    pathKeys = new Set();
    const summary = document.getElementById("world-path-summary");
    if (summary) summary.textContent = "";
    setWorldPathMsg("");
    if (lastLinks.length) updateLinks(lastLinks);
    else viewer?.scene.requestRender();
}

function setUsageMessage(text, isError = false) {
    const element = document.getElementById("world-usage-msg");
    if (!element) return;
    element.textContent = text;
    element.style.color = isError ? "var(--bad)" : "var(--muted)";
}

function rerenderLinks() {
    if (lastLinks.length) updateLinks(lastLinks);
    else viewer?.scene.requestRender();
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
                .filter(entry => entry && entry.src && entry.dst)
                .map(entry => [linkKey(entry.src, entry.dst), entry.utilization]),
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
        usageTimer = setInterval(refreshUsage, 5000);
    } else {
        usageByLink.clear();
        usageAvailable = false;
        setUsageMessage("");
        rerenderLinks();
    }
}

function bindUsageControl() {
    const checkbox = document.getElementById("cb-link-usage");
    if (!checkbox) return;
    checkbox.addEventListener("change", () => setUsageEnabled(checkbox.checked));
    window.addEventListener("pagehide", () => {
        if (usageTimer !== null) clearInterval(usageTimer);
        usageTimer = null;
    }, { once: true });
}

function bindWorldPathControls() {
    document
        .getElementById("world-path-trace")
        ?.addEventListener("click", traceWorldPath);
    document
        .getElementById("world-path-clear")
        ?.addEventListener("click", clearWorldPath);
}

let pollTimer = null;

function poll() {
    updateWorld().finally(() => {
        pollTimer = setTimeout(poll, 2000);
    });
}

function startWorld() {
    initCesium();
    initSimulationControls({ poll: true });
    bindWorldPathControls();
    bindUsageControl();
    loadWorldPathNodes();

    const cbMap = [
        ["cb-satellites", "satellites"],
        ["cb-ground-stations", "groundStations"],
        ["cb-gsl", "gsl"],
        ["cb-orbital", "orbital"],
        ["cb-adjacent", "adjacent"],
    ];
    cbMap.forEach(([id, key]) => {
        const el = document.getElementById(id);
        if (!el) return;
        el.checked = vis[key];
        el.addEventListener("change", () => {
            vis[key] = el.checked;
            applyVisibility();
        });
    });

    const cbCoverage = document.getElementById("cb-coverage");
    if (cbCoverage) {
        cbCoverage.checked = coverage.enabled;
        cbCoverage.addEventListener("change", () => {
            coverage.enabled = cbCoverage.checked;
            if (coverage.enabled) {
                // Immediately create circles for all known satellites without
                // waiting for the next 2-second poll.
                Object.entries(satPositions).forEach(([name, pos]) => {
                    updateCoverageCircle(name, pos.latDeg, pos.lonDeg, pos.altKm);
                });
                viewer.scene.requestRender();
            } else {
                applyCoverageVisibility();
            }
        });
    }

    const slElevation = document.getElementById("sl-elevation");
    const slElevationVal = document.getElementById("sl-elevation-val");
    if (slElevation) {
        slElevation.value = coverage.elevationDeg;
        slElevation.addEventListener("input", () => {
            coverage.elevationDeg = parseFloat(slElevation.value);
            if (slElevationVal) slElevationVal.textContent = slElevation.value;
            if (coverage.enabled) applyCoverageElevation();
        });
    }

    const slOpacity = document.getElementById("sl-opacity");
    const slOpacityVal = document.getElementById("sl-opacity-val");
    if (slOpacity) {
        slOpacity.value = Math.round(coverage.opacity * 100);
        slOpacity.addEventListener("input", () => {
            coverage.opacity = parseFloat(slOpacity.value) / 100;
            if (slOpacityVal) slOpacityVal.textContent = slOpacity.value + "%";
            if (coverage.enabled) applyCoverageOpacity();
        });
    }

    // Clicking a satellite dot or its coverage circle selects it (dims all others).
    // Clicking empty space or a ground station deselects.
    const clickHandler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    clickHandler.setInputAction((click) => {
        const picked = viewer.scene.pick(click.position);
        let satName = null;

        if (Cesium.defined(picked) && Cesium.defined(picked.id)) {
            const entity = picked.id;
            satName = Object.keys(satEntities).find(n => satEntities[n] === entity)
                || Object.keys(coverageEntities).find(n => coverageEntities[n].entity === entity)
                || null;
        }

        const prev = coverage.selectedSat;
        coverage.selectedSat = (satName !== null && satName !== prev) ? satName : null;

        if (coverage.enabled) {
            applyCoverageOpacity();
        }
    }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

    const panelHeader = document.getElementById("plot-controls-header");
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
