"""Unit tests for honeypot orchestration."""

import pytest

from satgonetem_gui.errors import APIError
from satgonetem_gui.schemas import HoneypotRequest
from satgonetem_gui.services.honeypot_service import HoneypotService


class FakeTopology:
    def __init__(self, running=True):
        self.running = running

    def require_topology(self):
        return object()

    def gonetem_is_on(self):
        return self.running


class FakeGateway:
    def __init__(self):
        self.calls = []

    def start(self, topology, node, port):
        self.calls.append(("start", node, port))
        return {"node": node, "port": port, "running": True, "events": []}

    def status(self, topology, node, port):
        self.calls.append(("status", node, port))
        return {"node": node, "port": port, "running": False, "events": []}

    def stop(self, topology, node, port):
        self.calls.append(("stop", node, port))


def test_start_requires_containers() -> None:
    service = HoneypotService(FakeTopology(running=False), FakeGateway())

    with pytest.raises(APIError) as error:
        service.start(HoneypotRequest(node="Gnd24", port=2222))

    assert error.value.status_code == 409


def test_start_status_stop_delegate() -> None:
    gateway = FakeGateway()
    service = HoneypotService(FakeTopology(), gateway)

    assert service.start(HoneypotRequest(node="Gnd24", port=2222))["running"] is True
    assert service.status("Gnd24", 2222)["running"] is False
    service.stop("Gnd24", 2222)

    assert gateway.calls == [
        ("start", "Gnd24", 2222),
        ("status", "Gnd24", 2222),
        ("stop", "Gnd24", 2222),
    ]
