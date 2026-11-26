"""Shared runtime setup and topology helpers for the core-facing adapters."""

import logging
import re
from typing import Any

from satgonetem.utils.satcom_fix import apply_satcom_fix

from ..resources import GROUND_STATIONS_DIR

logger = logging.getLogger(__name__)

DATA_SEARCH_DIR = GROUND_STATIONS_DIR
SPEED_OF_LIGHT_KM_PER_MS = 299.792458
PATH_NOTE = (
    "Computed over the current routing graph; this is a diagnostic path, "
    "not the live forwarding table."
)

_CORE_INITIALIZED = False


def initialize_core() -> None:
    """Apply the pinned core's performance patch once, outside module import."""
    global _CORE_INITIALIZED
    if not _CORE_INITIALIZED:
        apply_satcom_fix()
        _CORE_INITIALIZED = True


def display_name(topology: Any) -> str:
    """Return the user-facing project name without the timestamp suffix."""
    simulation_property = getattr(topology, "simulation_property", None)
    name = (
        getattr(simulation_property, "simulation_name", None) if simulation_property else None
    )
    if not name:
        raw_name = str(getattr(topology, "project_name", "") or "Loaded Project")
        name = re.sub(r"(?:_\d+)+$", "", raw_name)
    return str(name).strip() or "Loaded Project"


def addressable_endpoints(topology: Any) -> list[tuple[str, Any]]:
    """Return ground stations then addressable satellites with interfaces.

    Ground stations come first, each group ordered by the core object id, so
    the traffic picker and the connectivity matrix share one endpoint policy.
    """
    endpoints: list[tuple[str, Any]] = []
    for station in sorted(
        topology.ground_stations.values(),
        key=lambda node: node.id,
    ):
        if station.interfaces:
            endpoints.append(("ground_station", station))
    for satellite in sorted(
        topology.satellites.values(),
        key=lambda node: node.id,
    ):
        if satellite.is_addressable() and satellite.interfaces:
            endpoints.append(("satellite", satellite))
    return endpoints
