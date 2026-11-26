/**
 * Coverage circles for the World View.
 *
 * Pure satellite footprint geometry plus the Cesium ellipse entity lifecycle.
 * The page controller injects the viewer, its render request, and a lookup for
 * the latest satellite positions; this module owns no imports of world.js.
 */

import { byId } from "./dom.js";
import { retainedSelection } from "./world_model.js?v=3";

const EARTH_RADIUS_KM = 6371.0;

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
export function coverageRadiusMeters(altKm, elevationDeg) {
    const elRad = (elevationDeg * Math.PI) / 180;
    const sinRho = (EARTH_RADIUS_KM * Math.cos(elRad)) / (EARTH_RADIUS_KM + altKm);
    const rhoRad = Math.asin(Math.min(1, sinRho));
    const lambdaRad = Math.PI / 2 - elRad - rhoRad;
    return Math.max(0, EARTH_RADIUS_KM * 1000 * lambdaRad);
}

/**
 * Build the coverage-circle controller.
 *
 * @param {Object} deps
 * @param {Cesium.Viewer} deps.viewer - Viewer that owns the ellipse entities.
 * @param {Function} deps.requestRender - Request a viewer render.
 * @param {Function} deps.getSatellitePositions - Returns [name, position] entries
 *   for every satellite with a known position.
 * @returns {Object} Coverage state accessors and entity operations.
 */
export function createWorldCoverage({
    viewer,
    requestRender,
    getSatellitePositions,
}) {
    // Per-satellite coverage entity records: { entity, altKm }.
    const entities = {};
    const state = {
        enabled: false,
        elevationDeg: 10,
        opacity: 0.40,
        selectedSat: null,
    };

    /**
     * Return the effective fill opacity for a coverage circle.
     * When a satellite is selected, non-selected circles are dimmed to 15%.
     *
     * @param {string} satName
     * @returns {number} Opacity in [0, 1].
     */
    function getEffectiveOpacity(satName) {
        if (state.selectedSat === null) return state.opacity;
        return satName === state.selectedSat ? state.opacity : state.opacity * 0.15;
    }

    /**
     * Create or update the coverage circle Cesium entity for a satellite.
     * The entity is always kept in sync with the satellite position; its
     * visibility is controlled separately via state.enabled.
     *
     * @param {string} satName
     * @param {number} latDeg
     * @param {number} lonDeg
     * @param {number} altKm
     */
    function updateCoverageCircle(satName, latDeg, lonDeg, altKm) {
        const radius = coverageRadiusMeters(altKm, state.elevationDeg);
        const opacity = getEffectiveOpacity(satName);
        const groundPos = Cesium.Cartesian3.fromDegrees(lonDeg, latDeg, 0);

        if (entities[satName]) {
            const c = entities[satName];
            c.entity.position = groundPos;
            c.entity.ellipse.semiMajorAxis = radius;
            c.entity.ellipse.semiMinorAxis = radius;
            c.entity.ellipse.material = Cesium.Color.YELLOW.withAlpha(opacity);
            c.entity.show = state.enabled;
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
                    outlineColor: Cesium.Color.ORANGE.withAlpha(
                        Math.min(1, opacity * 2),
                    ),
                },
                show: state.enabled,
            });
            entities[satName] = { entity, altKm };
        }
    }

    /** Remove one satellite's coverage circle, if it still exists. */
    function removeSatellite(satName) {
        const entry = entities[satName];
        if (!entry) return;
        viewer.entities.remove(entry.entity);
        delete entities[satName];
    }

    /** Map a picked Cesium entity back to its satellite name. */
    function satelliteForEntity(entity) {
        return (
            Object.keys(entities).find(
                (name) => entities[name].entity === entity,
            ) || null
        );
    }

    /** Show or hide all coverage circle entities based on state.enabled. */
    function applyCoverageVisibility() {
        Object.values(entities).forEach((c) => {
            c.entity.show = state.enabled;
        });
        requestRender();
    }

    /**
     * Recalculate and apply fill opacity for every coverage circle.
     * Called when the opacity slider changes or a satellite is selected.
     */
    function applyCoverageOpacity() {
        Object.entries(entities).forEach(([name, c]) => {
            const op = getEffectiveOpacity(name);
            c.entity.ellipse.material = Cesium.Color.YELLOW.withAlpha(op);
            c.entity.ellipse.outlineColor = Cesium.Color.ORANGE.withAlpha(
                Math.min(1, op * 2),
            );
        });
        requestRender();
    }

    /** Recalculate and apply coverage radii for all circles. */
    function applyCoverageElevation() {
        Object.entries(entities).forEach(([, c]) => {
            const radius = coverageRadiusMeters(c.altKm, state.elevationDeg);
            c.entity.ellipse.semiMajorAxis = radius;
            c.entity.ellipse.semiMinorAxis = radius;
        });
        requestRender();
    }

    /** Select (or deselect) the satellite whose circle stays fully opaque. */
    function selectSatellite(satName) {
        state.selectedSat = satName ?? null;
        if (state.enabled) applyCoverageOpacity();
    }

    /** Drop the selection when its satellite is no longer present. */
    function retainSelection(names) {
        const retained = retainedSelection(state.selectedSat, names);
        if (retained !== state.selectedSat) {
            state.selectedSat = retained;
            if (state.enabled) applyCoverageOpacity();
        }
    }

    /**
     * Toggle coverage. Enabling creates circles for every known satellite
     * immediately instead of waiting for the next poll; disabling hides them.
     */
    function setEnabled(enabled) {
        state.enabled = Boolean(enabled);
        if (state.enabled) {
            (getSatellitePositions() || []).forEach(([name, pos]) => {
                updateCoverageCircle(name, pos.latDeg, pos.lonDeg, pos.altKm);
            });
            requestRender();
        } else {
            applyCoverageVisibility();
        }
    }

    /** Wire the coverage checkbox and the elevation/opacity sliders. */
    function bindControls() {
        const checkbox = byId("cb-coverage");
        if (checkbox) {
            checkbox.checked = state.enabled;
            checkbox.addEventListener("change", () => {
                setEnabled(checkbox.checked);
            });
        }

        const elevation = byId("sl-elevation");
        const elevationValue = byId("sl-elevation-val");
        if (elevation) {
            elevation.value = state.elevationDeg;
            elevation.addEventListener("input", () => {
                state.elevationDeg = parseFloat(elevation.value);
                if (elevationValue) elevationValue.textContent = elevation.value;
                if (state.enabled) applyCoverageElevation();
            });
        }

        const opacity = byId("sl-opacity");
        const opacityValue = byId("sl-opacity-val");
        if (opacity) {
            opacity.value = Math.round(state.opacity * 100);
            opacity.addEventListener("input", () => {
                state.opacity = parseFloat(opacity.value) / 100;
                if (opacityValue) opacityValue.textContent = opacity.value + "%";
                if (state.enabled) applyCoverageOpacity();
            });
        }
    }

    return {
        getEffectiveOpacity,
        updateCoverageCircle,
        removeSatellite,
        satelliteForEntity,
        applyCoverageVisibility,
        applyCoverageOpacity,
        applyCoverageElevation,
        selectSatellite,
        retainSelection,
        setEnabled,
        bindControls,
        isEnabled: () => state.enabled,
    };
}
