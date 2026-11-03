"""Unit tests for service orchestration with fake gateways."""

import asyncio

import pytest

from satgonetem_gui.errors import APIError
from satgonetem_gui.schemas import Iperf3Request, PingRequest
from satgonetem_gui.services.ports import TrafficPoll
from satgonetem_gui.services.routing_service import RoutingService
from satgonetem_gui.services.topology_service import TopologyService
from satgonetem_gui.services.traffic_service import TrafficService
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


class FakeController:
    """Minimal routing controller for service tests."""

    def routing_status(self, topology):
        return {
            "ok": True,
            "gonetem_is_on": False,
            "addressing_applied": False,
            "routing_initiated": False,
            "routing_method": "static",
        }

    def apply_routing(self, topology, method):
        raise AssertionError("should not run while GoNetEm is stopped")


class FakeTraffic:
    """Minimal traffic gateway for service tests."""

    def poll(self, flow):
        return TrafficPoll("done", results={"ok": True})


def _loaded_session() -> ProjectSession:
    session = ProjectSession()
    session.succeed(object(), "Project", "")
    return session


def test_topology_status_is_empty_without_a_project() -> None:
    """The dashboard can read an empty status before a project is loaded."""
    service = TopologyService(ProjectSession(), FakeReader())

    assert service.status()["constellation_loaded"] is False
    assert service.status()["satellites"] == 0


def test_topology_queries_require_a_project() -> None:
    """Read routes raise the common 404 when nothing is loaded."""
    service = TopologyService(ProjectSession(), FakeReader())

    with pytest.raises(APIError) as error:
        service.satellites()

    assert error.value.status_code == 404


def test_routing_apply_requires_gonetem() -> None:
    """Routing is rejected while the containers are stopped."""
    session = _loaded_session()
    topology = TopologyService(session, FakeReader(gonetem=False))
    service = RoutingService(topology, FakeController())

    with pytest.raises(APIError) as error:
        asyncio.run(service.apply("static"))

    assert error.value.status_code == 409


def test_traffic_requires_a_project() -> None:
    """Traffic cannot start before a project is loaded."""
    topology = TopologyService(ProjectSession(), FakeReader())
    service = TrafficService(topology, FakeTraffic())

    with pytest.raises(APIError) as error:
        service.start_iperf3(Iperf3Request(src="Sat0", dst="Sat0"))

    assert error.value.status_code == 404


def test_traffic_requires_gonetem() -> None:
    """Traffic cannot start while the containers are stopped."""
    topology = TopologyService(_loaded_session(), FakeReader(gonetem=False))
    service = TrafficService(topology, FakeTraffic())

    with pytest.raises(APIError) as error:
        service.start_iperf3(Iperf3Request(src="Sat0", dst="Sat0"))

    assert error.value.status_code == 409


def test_traffic_start_status_and_cancel() -> None:
    """A started job is pollable and cancellable through the service."""
    topology = TopologyService(_loaded_session(), FakeReader(gonetem=True))

    class FakeStarter(FakeTraffic):
        def start_ping(self, source, destination, request):
            return object()

    service = TrafficService(topology, FakeStarter())
    job_id = service.start_ping(PingRequest(src="Sat0", dst="Sat0"))

    assert job_id.startswith("j")
    assert service.status(job_id) == {"status": "done", "results": {"ok": True}}
    service.cancel(job_id)
    assert service.jobs.get(job_id).status == "cancelled"
