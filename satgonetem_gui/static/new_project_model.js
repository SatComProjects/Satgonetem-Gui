/** Pure helpers for the new-project form. */

export function normalizeProjectName(value) {
  return String(value ?? "").trim();
}

export function validateShellNumbers(planes, satellitesPerPlane, inclination, revolutions) {
  if (!Number.isInteger(planes) || planes < 1 || planes > 1000) {
    return "Planes must be an integer between 1 and 1000.";
  }
  if (
    !Number.isInteger(satellitesPerPlane) ||
    satellitesPerPlane < 1 ||
    satellitesPerPlane > 1000
  ) {
    return "Satellites per plane must be an integer between 1 and 1000.";
  }
  if (planes * satellitesPerPlane > 10000) {
    return "A shell cannot exceed 10000 satellites.";
  }
  if (!Number.isFinite(inclination) || inclination < 0 || inclination > 180) {
    return "Inclination must be between 0 and 180 degrees.";
  }
  if (!Number.isFinite(revolutions) || revolutions < 0 || revolutions > 100) {
    return "Revolutions per day must be between 0 and 100.";
  }
  return null;
}

export function validateGroundNumbers(elevation, maxConnected) {
  if (!Number.isFinite(elevation) || elevation < 0 || elevation > 90) {
    return "Elevation must be between 0 and 90 degrees.";
  }
  if (!Number.isInteger(maxConnected) || maxConnected < 1 || maxConnected > 10000) {
    return "Maximum connected satellites must be between 1 and 10000.";
  }
  return null;
}
