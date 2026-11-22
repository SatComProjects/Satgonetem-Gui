"""SatGoNetem coverage snapshot adapter.

This is the only module that imports the core coverage helpers. Services use
the narrow :class:`~satgonetem_gui.services.ports.CoverageController` protocol.
"""

import time
from collections.abc import Mapping
from typing import Any

from satgonetem.link_budget.geometry import get_elevation_angle
from satgonetem.utils.satellite_coverage import coverage_percentage_fast

UNASSIGNED_SHELL = "Unassigned"


def _position_tuple(position: Any) -> tuple[float, float, float] | None:
    """Return a ``(latitude, longitude, altitude)`` tuple, or None if malformed."""
    if not isinstance(position, Mapping):
        return None
    try:
        return (
            float(position["latitude"]),
            float(position["longitude"]),
            float(position["altitude"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _name(node: Any) -> str:
    """Return a display name for a satellite or ground station."""
    return str(getattr(node, "name", None) or "Unknown")


class SatGoNetemCoverageAdapter:
    """Concrete adapter around the public core coverage helpers."""

    def coverage_snapshot(
        self,
        topology: Any,
        *,
        elevation_deg: float,
        grid_resolution_deg: float,
        include_shells: bool,
        include_ground_stations: bool,
        max_shells: int,
        max_ground_stations: int,
    ) -> dict[str, Any]:
        """Measure overall, per-shell, and per-station coverage for a topology."""
        started = time.perf_counter()
        satellites = list(topology.satellites.values())
        overall = float(
            topology.get_coverage_percentage(
                elev_min_deg=elevation_deg,
                grid_res_deg=grid_resolution_deg,
            )
        )

        shells: list[dict[str, Any]] = []
        shells_truncated = False
        if include_shells:
            shells, shells_truncated = self._shell_results(
                satellites,
                elevation_deg=elevation_deg,
                grid_resolution_deg=grid_resolution_deg,
                max_shells=max_shells,
            )

        ground_stations: list[dict[str, Any]] = []
        ground_stations_truncated = False
        if include_ground_stations:
            ground_stations, ground_stations_truncated = self._ground_station_results(
                topology,
                satellites,
                elevation_deg=elevation_deg,
                max_ground_stations=max_ground_stations,
            )

        duration_ms = (time.perf_counter() - started) * 1000.0
        return {
            "coverage_percent": round(overall, 2),
            "satellites": len(satellites),
            "duration_ms": round(duration_ms, 1),
            "shells": shells,
            "ground_stations": ground_stations,
            "shells_truncated": shells_truncated,
            "ground_stations_truncated": ground_stations_truncated,
        }

    def _shell_results(
        self,
        satellites: list[Any],
        *,
        elevation_deg: float,
        grid_resolution_deg: float,
        max_shells: int,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Return per-shell coverage for the first ``max_shells`` identifiers."""
        groups: dict[str, list[Any]] = {}
        for satellite in satellites:
            identifier = getattr(getattr(satellite, "shell", None), "identifier", None)
            key = str(identifier) if identifier else UNASSIGNED_SHELL
            groups.setdefault(key, []).append(satellite)

        identifiers = sorted(groups)
        limit = max(0, int(max_shells))
        selected = identifiers[:limit]
        results = []
        for identifier in selected:
            group = groups[identifier]
            percent = coverage_percentage_fast(
                sats=group,
                elev_min_deg=elevation_deg,
                grid_res_deg=grid_resolution_deg,
            )
            results.append(
                {
                    "identifier": identifier,
                    "satellites": len(group),
                    "coverage_percent": round(float(percent), 2),
                }
            )
        return results, len(identifiers) > len(selected)

    def _ground_station_results(
        self,
        topology: Any,
        satellites: list[Any],
        *,
        elevation_deg: float,
        max_ground_stations: int,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Return the best satellite and covered state per ground station."""
        stations = list(topology.ground_stations.values())
        limit = max(0, int(max_ground_stations))
        selected = stations[:limit]
        results = []
        for station in selected:
            station_position = _position_tuple(getattr(station, "position", None))
            best_name: str | None = None
            best_elevation: float | None = None
            if station_position is not None:
                for satellite in satellites:
                    satellite_position = _position_tuple(getattr(satellite, "position", None))
                    if satellite_position is None:
                        continue
                    elevation = float(get_elevation_angle(satellite_position, station_position))
                    if best_elevation is None or elevation > best_elevation:
                        best_elevation = elevation
                        best_name = _name(satellite)
            results.append(
                {
                    "name": _name(station),
                    "covered": (best_elevation is not None and best_elevation >= elevation_deg),
                    "best_satellite": best_name,
                    "best_elevation_deg": (
                        None if best_elevation is None else round(best_elevation, 2)
                    ),
                }
            )
        return results, len(stations) > len(selected)
