"""Opt-in real-container check for the SatSec labs.

Enable with SATGONETEM_RUN_CONTAINER_TESTS=1 and a running GoNetEm server.
The default suite never starts Docker.
"""

import asyncio
import json
import os
import time

import pytest

from satgonetem_gui.adapters.satgonetem_security import SatGoNetemSecurityAdapter
from satgonetem_gui.adapters.satgonetem_topology import SatGoNetemTopologyAdapter
from satgonetem_gui.resources import GROUND_STATIONS_DIR, SECURITY_DIR
from satgonetem_gui.schemas import CaptureStartRequest, ProjectCreateRequest
from satgonetem_gui.services.project_service import ProjectService
from satgonetem_gui.services.routing_service import RoutingService
from satgonetem_gui.services.security_service import SecurityService
from satgonetem_gui.services.topology_service import TopologyService
from satgonetem_gui.state import RuntimeState

pytestmark = pytest.mark.slow


@pytest.mark.skipif(
    os.getenv("SATGONETEM_RUN_CONTAINER_TESTS") != "1",
    reason="set SATGONETEM_RUN_CONTAINER_TESTS=1 to run container tests",
)
def test_real_security_capture_failure_and_reset(settings) -> None:
    """Start the SatSec range, fail a link, capture a pcap, and reset."""
    data = json.loads((SECURITY_DIR / "range.json").read_text(encoding="utf-8"))
    payload = ProjectCreateRequest(
        name="SatSecContainerCheck",
        start_date=data["start_date"],
        end_date=data["end_date"],
        update_time=data.get("update_time", 5),
        isl_capacity=data.get("isl_capacity", 5000),
        gs_capacity=data.get("gs_capacity", 5000),
        walker_shells_json=json.dumps(data["walker_shells"]),
        ground_objects_properties_json=json.dumps(
            data["ground_objects_properties"]
        ),
    )

    adapter = SatGoNetemTopologyAdapter(settings)
    security_adapter = SatGoNetemSecurityAdapter()
    result = adapter.build(payload)
    topology_manager = result.topology_manager

    runtime = RuntimeState()
    runtime.project.succeed(topology_manager, result.project_name, "")
    topology = TopologyService(runtime.project, adapter)
    project = ProjectService(runtime, adapter, settings, GROUND_STATIONS_DIR)
    routing = RoutingService(topology, adapter)
    security = SecurityService(topology, routing, project, security_adapter)

    try:
        asyncio.run(routing.start_gonetem())
        asyncio.run(routing.apply("static"))

        links = adapter.links(topology_manager)
        assert len(links) > 0
        assert all(link["capacity_kbps"] == 5000 for link in links)

        key = next(
            link["key"]
            for link in links
            if link["type"] == "InterSatelliteLink"
        )
        security.fail_link(key)
        assert key in security.range()["failed_links"]

        node = topology_manager.get_node_by_name("Sat0")
        interface = node.interfaces[0].get_iname()
        capture = security.start_capture(
            CaptureStartRequest(
                node="Sat0",
                interface=interface,
                packet_limit=20,
                duration_sec=5,
            )
        )
        time.sleep(6)
        security.stop_capture(capture["id"])
        payload_bytes, filename = security.capture_bytes(capture["id"])
        assert filename.endswith(".pcap")
        assert payload_bytes[:4] == b"\xd4\xc3\xb2\xa1"

        asyncio.run(security.reset())
        restored = security.range()
        assert restored["failed_links"] == []
        assert len(restored["links"]) == len(links)
        assert restored["readiness"]["gonetem_is_on"] is True
    finally:
        try:
            asyncio.run(routing.stop_gonetem())
        except Exception:
            pass
