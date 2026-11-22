"""Preflight environment diagnostics and project size estimates."""

from __future__ import annotations

import json
import logging
from typing import Any

from ..errors import APIError
from ..schemas import PreflightRequest
from .ports import EnvironmentDoctor

logger = logging.getLogger(__name__)

ESTIMATED_MB_PER_CONTAINER = 128
LARGE_PROJECT_CONTAINERS = 200


def _count_value(entry: dict[str, Any], key: str, label: str) -> int:
    """Read one non-negative integer count from a project configuration entry."""
    value = entry.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be a non-negative integer.")
    if value < 0:
        raise ValueError(f"{label} must not be negative.")
    return value


def _count_satellites(shells: list[Any]) -> int:
    """Sum the satellites declared by every Walker shell."""
    total = 0
    for index, shell in enumerate(shells):
        if not isinstance(shell, dict):
            raise ValueError(f"Walker shell {index + 1} must be an object.")
        constellation = shell.get("constellation_property")
        if not isinstance(constellation, dict):
            raise ValueError(
                f"Walker shell {index + 1} is missing constellation_property."
            )
        planes = _count_value(
            constellation,
            "amount_of_orbit_plane",
            f"Walker shell {index + 1} amount_of_orbit_plane",
        )
        per_plane_key = "amount_of_satellite_per_orbit_plane"
        if per_plane_key not in constellation:
            per_plane_key = "amount_of_satellite_per_plane"
        per_plane = _count_value(
            constellation,
            per_plane_key,
            f"Walker shell {index + 1} {per_plane_key}",
        )
        total += planes * per_plane
    return total


def _count_ground_stations(grounds: list[Any]) -> tuple[int, int]:
    """Return the inline station count and the number of unknown data_file objects."""
    total = 0
    unknown = 0
    for index, ground in enumerate(grounds):
        if not isinstance(ground, dict):
            raise ValueError(f"Ground object {index + 1} must be an object.")
        stations = ground.get("stations")
        if stations is not None and not isinstance(stations, list):
            raise ValueError(f"Ground object {index + 1} stations must be a list.")
        if stations:
            total += len(stations)
        elif isinstance(ground.get("data_file"), str) and ground["data_file"].strip():
            unknown += 1
    return total, unknown


def estimate_project(shells: list[Any], grounds: list[Any]) -> dict[str, Any]:
    """Return a rough container and memory estimate for a submitted project.

    Args:
        shells: Parsed Walker shell objects.
        grounds: Parsed ground-object properties.

    Raises:
        ValueError: If the payload is not a pair of lists of objects with
            non-negative integer constellation counts.
    """
    if not isinstance(shells, list):
        raise ValueError("Walker shells must be a list.")
    if not isinstance(grounds, list):
        raise ValueError("Ground objects must be a list.")

    satellites = _count_satellites(shells)
    ground_stations, unknown_data_files = _count_ground_stations(grounds)
    containers = satellites + ground_stations

    warnings: list[str] = []
    if unknown_data_files:
        warnings.append(
            f"{unknown_data_files} ground object(s) use data_file; their station "
            "counts are not included in this estimate."
        )
    if containers > LARGE_PROJECT_CONTAINERS:
        warnings.append(
            f"{containers} containers is a large constellation; expect higher "
            "memory use and longer build times."
        )

    return {
        "satellites": satellites,
        "ground_stations": ground_stations,
        "containers": containers,
        "estimated_memory_mb": containers * ESTIMATED_MB_PER_CONTAINER,
        "note": (
            "Rough estimate only: assumes each satellite and ground station runs "
            f"as one container using about {ESTIMATED_MB_PER_CONTAINER} MB. "
            "Actual usage depends on the container images and enabled services."
        ),
        "warnings": warnings,
    }


def _parse_json_array(value: str | None, field: str) -> list[Any]:
    """Parse an optional JSON array field, treating empty input as an empty list."""
    if value is None or not value.strip():
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise APIError(
            422,
            f"Invalid project configuration: {field} must be valid JSON.",
        ) from exc
    if not isinstance(parsed, list):
        raise APIError(
            422,
            f"Invalid project configuration: {field} must be a JSON array.",
        )
    return parsed


class PreflightService:
    """Run environment checks and an optional project estimate."""

    def __init__(self, doctor: EnvironmentDoctor) -> None:
        self.doctor = doctor

    def run(self, payload: PreflightRequest | None) -> dict[str, Any]:
        """Return environment readiness plus an estimate when a payload was sent."""
        try:
            checks = list(self.doctor.environment_checks())
        except Exception as exc:
            logger.exception("Preflight environment checks failed.")
            raise APIError(500, "Could not run environment checks.") from exc

        estimate = None
        if payload is not None and (
            payload.walker_shells_json is not None
            or payload.ground_objects_properties_json is not None
        ):
            shells = _parse_json_array(payload.walker_shells_json, "walker_shells_json")
            grounds = _parse_json_array(
                payload.ground_objects_properties_json,
                "ground_objects_properties_json",
            )
            try:
                estimate = estimate_project(shells, grounds)
            except ValueError as exc:
                raise APIError(
                    422,
                    f"Invalid project configuration: {exc}",
                ) from exc

        blocking = any(check.get("status") == "error" for check in checks)
        return {
            # ``ok`` is the transport-level success flag shared by every JSON
            # response; ``blocking`` is the readiness signal. The browser client
            # treats ``ok: false`` as a request failure and would hide the checks.
            "ok": True,
            "blocking": blocking,
            "checks": checks,
            "estimate": estimate,
        }
