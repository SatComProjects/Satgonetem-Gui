"""Global application state for the SatGoNetem GUI."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from satgonetem.services.topology_satcom import TopologyManager  # type: ignore[import]


@dataclass
class AppState:
    """Holds the single shared TopologyManager instance and project metadata.

    Args:
        topology_manager: Active TopologyManager, or None when no project is loaded.
        project_name: Name of the currently loaded project, or None.
        creating: True while a project is being built in a background thread.
        jobs: Registry of active and completed traffic jobs keyed by job_id.
        jobs_lock: Lock protecting concurrent access to jobs.
    """

    topology_manager: Optional[TopologyManager] = None
    project_name: Optional[str] = None
    creating: bool = False
    jobs: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    jobs_lock: threading.Lock = field(default_factory=threading.Lock)

    def get_status_dict(self) -> Dict[str, Any]:
        """Return a serializable status snapshot for the dashboard.

        Returns:
            Dictionary with keys: constellation_loaded, satellites,
            ground_stations, links, gonetem_is_on, simulation_updating,
            current_step, current_time.
        """
        if self.topology_manager is None:
            return {
                "constellation_loaded": False,
                "satellites": 0,
                "ground_stations": 0,
                "links": 0,
                "gonetem_is_on": False,
                "simulation_updating": False,
                "current_step": None,
                "current_time": None,
            }

        tm = self.topology_manager
        try:
            summary = tm.get_topology_summary()
        except Exception:
            summary = {"satellites": 0, "ground_stations": 0, "links": 0}

        try:
            current_time = tm.get_current_time()
            current_time_str = current_time.isoformat() if current_time else None
        except Exception:
            current_time_str = None

        try:
            current_step = tm.get_current_time_step()
        except Exception:
            current_step = None

        return {
            "constellation_loaded": tm.get_status(),
            "satellites": summary.get("satellites", 0),
            "ground_stations": summary.get("ground_stations", 0),
            "links": summary.get("links", 0),
            "gonetem_is_on": tm.get_gonetem_status(),
            "simulation_updating": tm.get_running(),
            "current_step": current_step,
            "current_time": current_time_str,
        }


app_state = AppState()
