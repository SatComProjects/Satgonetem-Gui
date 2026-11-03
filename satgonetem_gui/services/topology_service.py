"""Read-only topology queries."""

from typing import Any

from ..errors import APIError
from ..state import ProjectSession
from .ports import TopologyReader


class TopologyService:
    """Serve topology views from the currently loaded project."""

    def __init__(self, session: ProjectSession, reader: TopologyReader) -> None:
        self.session = session
        self.reader = reader

    def require_topology(self) -> Any:
        """Return the loaded topology or raise the common 404."""
        topology = self.session.get_topology()
        if topology is None:
            raise APIError(404, "No project is currently loaded.")
        return topology

    def status(self) -> dict:
        """Return the dashboard status snapshot, including the empty state."""
        topology = self.session.get_topology()
        if topology is None:
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
        return self.reader.status(topology)

    def satellites(self) -> list[dict]:
        """Return satellite positions."""
        return self.reader.satellites(self.require_topology())

    def ground_stations(self) -> list[dict]:
        """Return ground-station positions."""
        return self.reader.ground_stations(self.require_topology())

    def links(self) -> list[dict]:
        """Return topology links."""
        return self.reader.links(self.require_topology())

    def nodes(self) -> list[dict]:
        """Return the node summary list."""
        return self.reader.nodes(self.require_topology())

    def node_detail(self, name: str) -> dict:
        """Return one node's details or raise 404."""
        detail = self.reader.node_detail(self.require_topology(), name)
        if detail is None:
            raise APIError(404, f"Node not found: {name}")
        return detail

    def find_node(self, name: str) -> Any | None:
        """Return a concrete node object for traffic setup."""
        return self.reader.find_node(self.require_topology(), name)

    def traffic_nodes(self) -> list[dict[str, str]]:
        """Return traffic source/destination options."""
        return self.reader.traffic_nodes(self.require_topology())

    def gonetem_is_on(self) -> bool:
        """Return whether the containers are running."""
        return self.reader.gonetem_is_on(self.require_topology())
