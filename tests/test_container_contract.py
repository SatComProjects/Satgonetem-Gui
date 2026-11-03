"""Opt-in contract test against real GoNetEm containers.

Enable with SATGONETEM_RUN_CONTAINER_TESTS=1. The default suite never starts
Docker; this test is intentionally slow and launches a 10x10 constellation.
"""

import os

import pytest

from satgonetem_gui.adapters.satgonetem_topology import SatGoNetemTopologyAdapter
from satgonetem_gui.schemas import ProjectCreateRequest
from tests.factories import project_payload

pytestmark = pytest.mark.slow


@pytest.mark.skipif(
    os.getenv("SATGONETEM_RUN_CONTAINER_TESTS") != "1",
    reason="set SATGONETEM_RUN_CONTAINER_TESTS=1 to run container tests",
)
def test_real_container_routing_lifecycle(settings) -> None:
    """Start, address, route, delete, and stop a real container network."""
    adapter = SatGoNetemTopologyAdapter(settings)
    result = adapter.build(ProjectCreateRequest(**project_payload("ContainerContract")))
    topology = result.topology_manager
    try:
        adapter.start_gonetem(topology)
        assert adapter.gonetem_is_on(topology) is True

        adapter.apply_addressing(topology)
        adapter.init_routing(topology, "static")
        status = adapter.routing_status(topology)
        assert status["gonetem_is_on"] is True
        assert status["routing_initiated"] is True

        adapter.delete_routing(topology)
        assert adapter.routing_status(topology)["routing_initiated"] is False
    finally:
        adapter.stop_gonetem(topology)
        assert adapter.gonetem_is_on(topology) is False
