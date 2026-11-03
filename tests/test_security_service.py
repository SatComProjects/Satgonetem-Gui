"""Unit tests for security-lab orchestration with fake collaborators."""

import asyncio

import pytest

from satgonetem_gui.errors import APIError
from satgonetem_gui.schemas import CaptureStartRequest
from satgonetem_gui.services.ports import NetworkOperationError
from satgonetem_gui.services.security_service import SecurityService
from satgonetem_gui.services.topology_service import TopologyService
from satgonetem_gui.state import ProjectSession


class FakeReader:
    """Minimal loaded topology for security service tests."""

    def status(self, topology):
        return {
            "constellation_loaded": True,
            "gonetem_is_on": True,
            "simulation_updating": False,
            "current_step": 0,
            "current_time": None,
            "satellites": 2,
            "ground_stations": 1,
            "links": 2,
        }

    def links(self, topology):
        return [
            {
                "key": "Gnd0|Sat0|GroundStationLink|bidirectional",
                "src": "Gnd0",
                "dst": "Sat0",
                "type": "GroundStationLink",
                "direction": "bidirectional",
                "distance_km": 500.0,
                "capacity_kbps": 5000,
                "delay_ms": 2,
                "state": "active",
            }
        ]

    def traffic_nodes(self, topology):
        return [
            {"name": "Gnd0", "type": "ground_station", "label": "Gnd0"},
            {"name": "Sat0", "type": "satellite", "label": "Sat0"},
        ]

    def gonetem_is_on(self, topology):
        return True


class FakeRouting:
    """Record routing lifecycle calls."""

    def __init__(self):
        self.calls = []

    def status(self):
        return {
            "addressing_applied": True,
            "routing_initiated": True,
            "routing_method": "static",
        }

    async def stop_gonetem(self):
        self.calls.append("stop")

    async def start_gonetem(self):
        self.calls.append("start")

    async def apply(self, method):
        self.calls.append(("apply", method))


class FakeProject:
    """Provide a snapshot and record restore calls."""

    current_name = "SecurityRange"

    def __init__(self):
        self.calls = []
        self.snapshot_calls = 0

    def snapshot(self):
        self.snapshot_calls += 1
        return '{"snapshot": true}'

    async def load(self, content):
        self.calls.append(("load", content))
        return "SecurityRange"


class FakeGateway:
    """Fake link and capture operations."""

    def __init__(self):
        self.fail_calls = []
        self.capture_starts = []
        self.capture_stops = []
        self.deleted = []
        self.payload = b"pcap"

    def routing_methods(self, topology):
        return ["static", "dynamic-ospf"]

    def fail_link(self, topology, key):
        self.fail_calls.append(key)
        return {"key": key}

    def start_capture(self, topology, node, interface, packet_limit, duration_sec):
        self.capture_starts.append((node, interface, packet_limit, duration_sec))
        return {"path": "/tmp/satsec_test.pcap", "interface": interface}

    def stop_capture(self, topology, node, path):
        self.capture_stops.append((node, path))

    def capture_status(self, topology, node, path):
        return {"size_bytes": 128, "running": False}

    def read_capture(self, topology, node, path):
        return self.payload

    def delete_capture(self, topology, node, path):
        self.deleted.append((node, path))


def _service(gateway=None):
    session = ProjectSession()
    session.succeed(object(), "SecurityRange", "")
    reader = FakeReader()
    topology = TopologyService(session, reader)
    routing = FakeRouting()
    project = FakeProject()
    gateway = gateway or FakeGateway()
    return SecurityService(topology, routing, project, gateway), project, routing, gateway


def test_range_reports_readiness_and_security_inventory() -> None:
    """The range response combines readiness, targets, links, and methods."""
    service, _project, _routing, _gateway = _service()

    data = service.range()

    assert data["project_name"] == "SecurityRange"
    assert data["readiness"]["gonetem_is_on"] is True
    assert data["readiness"]["addressing_applied"] is True
    assert data["nodes"][0]["name"] == "Gnd0"
    assert data["links"][0]["capacity_kbps"] == 5000
    assert data["routing_methods"] == ["static", "dynamic-ospf"]
    assert data["snapshot_available"] is False


def test_fail_link_snapshots_once_and_rejects_duplicates() -> None:
    """Failing a link snapshots the project before the destructive action."""
    service, project, _routing, gateway = _service()

    assert service.fail_link("Gnd0|Sat0|GroundStationLink|bidirectional") == {
        "key": "Gnd0|Sat0|GroundStationLink|bidirectional"
    }
    assert project.snapshot_calls == 1
    assert gateway.fail_calls == ["Gnd0|Sat0|GroundStationLink|bidirectional"]

    with pytest.raises(APIError) as error:
        service.fail_link("Gnd0|Sat0|GroundStationLink|bidirectional")
    assert error.value.status_code == 409


def test_fail_link_requires_running_containers() -> None:
    """A stopped range cannot be mutated."""
    service, _project, _routing, _gateway = _service()
    service.topology.reader.gonetem_is_on = lambda topology: False

    with pytest.raises(APIError) as error:
        service.fail_link("missing")

    assert error.value.status_code == 409


def test_reset_restores_snapshot_and_routing() -> None:
    """Reset stops, loads, restarts, and reapplies the saved routing method."""
    service, project, routing, _gateway = _service()
    service.fail_link("Gnd0|Sat0|GroundStationLink|bidirectional")

    result = asyncio.run(service.reset())

    assert result == {"restored": True, "containers_restarted": True}
    assert routing.calls == ["stop", "start", ("apply", "static")]
    assert project.calls == [("load", '{"snapshot": true}')]
    assert service.range()["failed_links"] == []


def test_capture_lifecycle() -> None:
    """Captures move from capturing to ready and can be downloaded."""
    service, project, _routing, gateway = _service()

    started = service.start_capture(
        CaptureStartRequest(node="Sat0", interface="eth0", packet_limit=10)
    )
    assert started["status"] == "capturing"
    assert project.snapshot_calls == 1

    listed = service.list_captures()
    assert listed[0]["status"] == "ready"
    assert listed[0]["size_bytes"] == 128

    payload, filename = service.capture_bytes(started["id"])
    assert payload == b"pcap"
    assert filename.endswith(".pcap")

    stopped = service.stop_capture(started["id"])
    assert stopped["status"] == "ready"
    assert gateway.capture_starts == [("Sat0", "eth0", 10, 15)]


def test_capture_reports_dependency_errors() -> None:
    """Adapter failures use the shared 500 envelope."""
    gateway = FakeGateway()

    def fail(*_args):
        raise NetworkOperationError("container unavailable")

    gateway.start_capture = fail
    service, _project, _routing, _gateway = _service(gateway)

    with pytest.raises(APIError) as error:
        service.start_capture(CaptureStartRequest(node="Sat0", interface="eth0"))

    assert error.value.status_code == 500
