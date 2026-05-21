"use strict";

const SAT_COLOR = Cesium.Color.fromCssColorString("#3b82f6");
const GS_CONN_COLOR = Cesium.Color.fromCssColorString("#22c55e");
const GS_DISC_COLOR = Cesium.Color.fromCssColorString("#dc2626");
const LINK_COLORS = {
    gsl: Cesium.Color.fromCssColorString("#16a34a").withAlpha(0.75),
    orbital: Cesium.Color.fromCssColorString("#1e40af").withAlpha(0.75),
    adjacent: Cesium.Color.fromCssColorString("#dc2626").withAlpha(0.75),
};

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
        const p = sat.position;
        const pos = toCartesian(p.latitude, p.longitude, p.altitude);
        nodePositions.set(sat.name, pos);
        seen.add(sat.name);

        if (satEntities[sat.name]) {
            satEntities[sat.name].position = pos;
            satEntities[sat.name].show = vis.satellites;
        } else {
            satEntities[sat.name] = viewer.entities.add({
                name: sat.name,
                position: pos,
                point: {
                    pixelSize: 5,
                    color: SAT_COLOR,
                },
                description: `<b>${sat.name}</b><br>Lat: ${p.latitude.toFixed(2)}<br>Lon: ${p.longitude.toFixed(2)}<br>Alt: ${p.altitude.toFixed(0)} km`,
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
        const p = gs.position;
        const pos = toCartesian(p.latitude, p.longitude, p.altitude);
        nodePositions.set(gs.name, pos);
        seen.add(gs.name);

        const color = connected.has(gs.name) ? GS_CONN_COLOR : GS_DISC_COLOR;
        const city = gs.city ? ` (${gs.city})` : "";
        const statusText = connected.has(gs.name) ? "Connected" : "Disconnected";

        if (gsEntities[gs.name]) {
            gsEntities[gs.name].position = pos;
            gsEntities[gs.name].point.color = color;
            gsEntities[gs.name].show = vis.groundStations;
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
                description: `<b>${gs.name}${city}</b><br>Lat: ${p.latitude.toFixed(2)}<br>Lon: ${p.longitude.toFixed(2)}<br>Status: ${statusText}`,
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
    Object.values(linkCollections).forEach(col => col.removeAll());

    links.forEach(lk => {
        const ltype = classifyLink(lk);
        const col = linkCollections[ltype];
        const src = nodePositions.get(lk.src);
        const dst = nodePositions.get(lk.dst);
        if (!src || !dst) return;

        col.add({
            positions: [src, dst],
            width: 1.0,
            material: Cesium.Material.fromType("Color", { color: LINK_COLORS[ltype] }),
        });
    });

    viewer.scene.requestRender();
}

/**
 * Fetch satellites, ground stations, and links from the API, then update the view.
 */
async function updateWorld() {
    try {
        const [satsRes, gsRes, linksRes] = await Promise.all([
            fetch("/api/satellites"),
            fetch("/api/ground_stations"),
            fetch("/api/links"),
        ]);

        const satellites = satsRes.ok ? await satsRes.json() : [];
        const groundStations = gsRes.ok ? await gsRes.json() : [];
        const links = linksRes.ok ? await linksRes.json() : [];

        if (!Array.isArray(satellites) || !Array.isArray(groundStations)) return;
        const linkArr = Array.isArray(links) ? links : [];

        const connected = connectedGsNames(linkArr);

        // Satellites and ground stations must be updated before links
        // so nodePositions contains fresh positions when link endpoints are resolved.
        updateSatellites(satellites);
        updateGroundStations(groundStations, connected);
        updateLinks(linkArr);
    } catch (err) {
        console.error("World update error:", err);
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
}

let pollTimer = null;

function poll() {
    updateWorld().finally(() => {
        pollTimer = setTimeout(poll, 2000);
    });
}

document.addEventListener("DOMContentLoaded", () => {
    initCesium();

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

    document.getElementById("plot-controls-header").addEventListener("click", togglePanel);

    poll();
});
