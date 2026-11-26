"""Opt-in contract test against real GoNetEm containers.

Enable with SATGONETEM_RUN_CONTAINER_TESTS=1. The default suite never starts
Docker; this test is intentionally slow and launches a 10x10 constellation.
"""

import os

import pytest

from satgonetem_gui.adapters.network_adapter import NetworkAdapter
from satgonetem_gui.adapters.project_adapter import ProjectAdapter
from satgonetem_gui.adapters.topology_reader import TopologyReaderAdapter
from satgonetem_gui.schemas import ProjectCreateRequest
from tests.factories import project_payload

pytestmark = pytest.mark.slow


@pytest.mark.skipif(
    os.getenv("SATGONETEM_RUN_CONTAINER_TESTS") != "1",
    reason="set SATGONETEM_RUN_CONTAINER_TESTS=1 to run container tests",
)
def test_real_container_routing_lifecycle(settings) -> None:
    """Start, address, route, delete, and stop a real container network."""
    project = ProjectAdapter(settings)
    network = NetworkAdapter()
    reader = TopologyReaderAdapter()
    result = project.build(ProjectCreateRequest(**project_payload("ContainerContract")))
    topology = result.topology_manager
    try:
        network.start_gonetem(topology)
        assert reader.gonetem_is_on(topology) is True

        network.apply_addressing(topology)
        network.init_routing(topology, "static")
        status = network.routing_status(topology)
        assert status["gonetem_is_on"] is True
        assert status["routing_initiated"] is True

        network.delete_routing(topology)
        assert network.routing_status(topology)["routing_initiated"] is False
    finally:
        network.stop_gonetem(topology)
        assert reader.gonetem_is_on(topology) is False
