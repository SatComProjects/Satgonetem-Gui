"""Read-only topology queries."""

import re
from typing import Any, cast

from ..errors import APIError
from ..state import ProjectSession
from .ports import LinkUsageReader, TopologyReader

_NODE_NAME_RE = re.compile(r"^(?:Sat|Gnd)\d+$")


def is_node_name(name: str) -> bool:
    """Return whether a name matches the core's ``Sat<id>``/``Gnd<id>`` form."""
    return bool(_NODE_NAME_RE.fullmatch(name))


class TopologyService:
    """Serve topology views from the currently loaded project."""

    def __init__(
        self,
        session: ProjectSession,
        reader: TopologyReader,
        usage_reader: LinkUsageReader | None = None,
    ) -> None:
        self.session = session
        self.reader = reader
        self.usage_reader = (
            usage_reader if usage_reader is not None else cast(LinkUsageReader, reader)
        )

    def require_topology(self) -> Any:
        """Return the loaded topology or raise the common 404."""
        topology = self.session.get_topology()
        if topology is None:
            raise APIError(404, "No project is currently loaded.")
        return topology

    def context(self) -> tuple[Any, int]:
        """Return the topology and generation from one locked snapshot."""
        topology, generation = self.session.topology_snapshot()
        if topology is None:
            raise APIError(404, "No project is currently loaded.")
        return topology, generation

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
                "total_steps": None,
                "simulation_rate": None,
                "last_simulation_error": None,
            }
        status = self.reader.status(topology)
        status["constellation_loaded"] = self.session.loaded
        return status

    def satellites(self) -> list[dict]:
        """Return satellite positions."""
        return self.reader.satellites(self.require_topology())

    def ground_stations(self) -> list[dict]:
        """Return ground-station positions."""
        return self.reader.ground_stations(self.require_topology())

    def links(self) -> list[dict]:
        """Return topology links."""
        return self.reader.links(self.require_topology())

    def link_usage(self) -> dict:
        """Return live link usage sampled from the running emulation."""
        return self.usage_reader.link_usage(self.require_topology())

    def nodes(self) -> list[dict]:
        """Return the node summary list."""
        return self.reader.nodes(self.require_topology())

    def node_detail(self, name: str) -> dict:
        """Return one node's details or raise 404."""
        topology = self.require_topology()
        if not is_node_name(name):
            raise APIError(404, f"Node not found: {name}")
        detail = self.reader.node_detail(topology, name)
        if detail is None:
            raise APIError(404, f"Node not found: {name}")
        return detail

    def find_node(self, name: str) -> Any | None:
        """Return a concrete node object for traffic setup."""
        topology = self.require_topology()
        if not is_node_name(name):
            return None
        return self.reader.find_node(topology, name)

    def traffic_nodes(self) -> list[dict[str, str]]:
        """Return traffic source/destination options."""
        return self.reader.traffic_nodes(self.require_topology())

    def gonetem_is_on(self) -> bool:
        """Return whether the containers are running."""
        return self.reader.gonetem_is_on(self.require_topology())

    def network_running(self) -> bool:
        """Return container state without requiring a loaded project."""
        topology = self.session.get_topology()
        return False if topology is None else self.reader.gonetem_is_on(topology)

    @property
    def generation(self) -> int:
        """Return the current project generation for stale-operation guards."""
        return self.session.generation

    @property
    def addressing_applied(self) -> bool:
        """Return whether IP addressing was applied to the current project."""
        return self.session.addressing_applied

    def set_addressing_applied(self, applied: bool) -> None:
        """Record addressing state for the current project."""
        self.session.set_addressing_applied(applied)
