"""Unit tests for topology queries and network-operation leases."""

import pytest

from satgonetem_gui.errors import APIError
from satgonetem_gui.services.topology_service import TopologyService
from satgonetem_gui.state import ProjectSession
from tests.service_fakes import FakeReader, _loaded_session


class FakeUsageReader:
    """Minimal link-usage reader for service tests."""

    def __init__(self, response=None) -> None:
        self.response = response or {
            "available": True,
            "sampled_at": "2024-01-01T00:00:00+00:00",
            "links": [],
            "note": None,
        }
        self.calls = []

    def link_usage(self, topology):
        self.calls.append(topology)
        return self.response


def test_topology_status_is_empty_without_a_project() -> None:
    """The dashboard can read an empty status before a project is loaded."""
    service = TopologyService(ProjectSession(), FakeReader())

    assert service.status()["constellation_loaded"] is False
    assert service.status()["satellites"] == 0


def test_topology_network_operation_lease_is_exclusive() -> None:
    """The lease holds one mutation at a time and releases on exit."""
    session = _loaded_session()
    service = TopologyService(session, FakeReader())

    with service.network_operation():
        assert session.network_operation is True
        assert service.begin_network_operation() is False
        with pytest.raises(APIError) as error:
            with service.network_operation():
                pass
        assert error.value.status_code == 409

    assert session.network_operation is False
    assert service.begin_network_operation() is True
    service.end_network_operation()
    assert session.network_operation is False


def test_topology_context_returns_the_topology_and_generation_together() -> None:
    """Routing reads both values from one session snapshot."""
    session = _loaded_session()
    service = TopologyService(session, FakeReader())

    topology, generation = service.context()

    assert topology is session.get_topology()
    assert generation == session.generation


def test_topology_queries_require_a_project() -> None:
    """Read routes raise the common 404 when nothing is loaded."""
    service = TopologyService(ProjectSession(), FakeReader())

    with pytest.raises(APIError) as error:
        service.satellites()

    assert error.value.status_code == 404


def test_topology_link_usage_requires_a_project() -> None:
    """Usage cannot be sampled before a project is loaded."""
    reader = FakeUsageReader()
    service = TopologyService(ProjectSession(), FakeReader(), usage_reader=reader)

    with pytest.raises(APIError) as error:
        service.link_usage()

    assert error.value.status_code == 404
    assert reader.calls == []


def test_topology_link_usage_returns_the_reader_payload() -> None:
    """The service forwards the installed topology to the usage reader."""
    session = _loaded_session()
    reader = FakeUsageReader()
    service = TopologyService(session, FakeReader(), usage_reader=reader)

    result = service.link_usage()

    assert result is reader.response
    assert reader.calls == [session.get_topology()]


def test_status_stays_loaded_after_containers_stop() -> None:
    """Project availability is independent of container status."""
    session = _loaded_session()

    class StoppedReader(FakeReader):
        def status(self, topology):
            data = super().status(topology)
            data["constellation_loaded"] = False
            return data

    service = TopologyService(session, StoppedReader())

    assert service.status()["constellation_loaded"] is True
