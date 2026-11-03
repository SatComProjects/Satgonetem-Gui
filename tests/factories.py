"""Factories for representative GUI test payloads."""

import json
from typing import Any

PROJECT_NAME = "Phase0Constellation"

# The Phase 0 integration fixture is a 10x10 Walker delta constellation.
PLANES = 10
SATELLITES_PER_PLANE = 10


def walker_shell(
    identifier: str = "LEO",
    planes: int = PLANES,
    satellites_per_plane: int = SATELLITES_PER_PLANE,
) -> dict[str, Any]:
    """Return a Walker delta shell with four inter-satellite links per node."""
    return {
        "type": "delta",
        "constellation_property": {
            "identifier": identifier,
            "amount_of_orbit_plane": planes,
            "amount_of_satellite_per_orbit_plane": satellites_per_plane,
            "inclination": 70,
            "phase_difference_between_satellites": True,
            "mean_revolution_per_day": 14.4,
        },
        "orbital_connectivity_property": {
            "adjacent_inter_satellite_shifting": 0,
            "maximum_inter_satellite_count": 4,
            "maximum_inter_satellite_range_distance": 1500.0,
            "maximum_ground_station_range": 1200.0,
            "maximum_user_terminal_range": 1000.0,
            "maximum_connected_ground_object": 10000,
            "maximum_connected_user_terminal": 500,
            "maximum_connected_ground_station": 10,
        },
        "ground_object_white_list": ["Ground Stations"],
    }


def ground_object() -> dict[str, Any]:
    """Return one Berlin ground object using the everything-visible strategy."""
    return {
        "identifier": "Ground Stations",
        "stations": [
            {
                "index": 0,
                "name": "Berlin",
                "latitude": 52.52,
                "longitude": 13.405,
                "elevation_km": 0.034,
            }
        ],
        "type": "ground_station",
        "connectivity_properties": {
            "ground_to_space_connections_strategy": "everything-visible",
            "elevation_above_horizon": 10,
            "maximum_satellite_range_distance": 1500.0,
            "shell_white_lists": ["LEO"],
            "maximum_connected_satellites": 3,
        },
    }


def project_payload(name: str = PROJECT_NAME, save_path: str = "") -> dict[str, Any]:
    """Return the JSON body accepted by POST /api/project/create."""
    return {
        "name": name,
        "update_time": "5",
        "start_date": "01/01/2024 00:00:00",
        "end_date": "01/01/2024 00:10:00",
        "isl_capacity": "100000",
        "gs_capacity": "100000",
        "save_path": save_path,
        "walker_shells_json": json.dumps([walker_shell()]),
        "ground_objects_properties_json": json.dumps([ground_object()]),
    }


def build_project(name: str = PROJECT_NAME, save_path: str = "") -> dict[str, Any]:
    """Build the 10x10 project synchronously and install it in the session."""
    from satgonetem_gui.app import _build_topology
    from satgonetem_gui.schemas import ProjectCreateRequest
    from satgonetem_gui.state import app_state

    payload = project_payload(name, save_path)
    tm = _build_topology(ProjectCreateRequest(**payload))
    tm.set_status(True)
    app_state.project.succeed(tm, name, save_path)
    return payload
