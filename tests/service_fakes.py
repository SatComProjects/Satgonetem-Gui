"""Shared fakes and helpers for the service orchestration tests."""

from satgonetem_gui.services.topology_service import TopologyService
from satgonetem_gui.state import ProjectSession


class FakeReader:
    """Minimal topology reader for service tests."""

    def __init__(self, gonetem: bool = False) -> None:
        self.gonetem = gonetem

    def status(self, topology):
        return {
            "constellation_loaded": True,
            "satellites": 1,
            "ground_stations": 0,
            "links": 0,
            "gonetem_is_on": self.gonetem,
            "simulation_updating": False,
            "current_step": 0,
            "current_time": None,
        }

    def satellites(self, topology):
        return [{"id": 0, "name": "Sat0", "position": {}}]

    def traffic_nodes(self, topology):
        return [{"name": "Sat0", "type": "satellite"}]

    def find_node(self, topology, name):
        return name if name == "Sat0" else None

    def gonetem_is_on(self, topology):
        return self.gonetem


def _loaded_session() -> ProjectSession:
    session = ProjectSession()
    session.succeed(object(), "Project", "")
    return session


def _ready_topology() -> TopologyService:
    """Return a loaded topology with addressing applied for traffic tests."""
    topology = TopologyService(_loaded_session(), FakeReader(gonetem=True))
    topology.set_addressing_applied(True)
    return topology
