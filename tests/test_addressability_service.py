"""Unit tests for satellite addressability orchestration."""

import pytest

from satgonetem_gui.errors import APIError
from satgonetem_gui.services.addressability_service import AddressabilityService
from satgonetem_gui.services.ports import NetworkOperationError
from satgonetem_gui.services.topology_service import TopologyService
from satgonetem_gui.state import ProjectSession
from tests.service_fakes import FakeReader, _loaded_session


class FakeAddressabilityController:
    """In-memory satellite addressability controller for service tests."""

    def __init__(
        self,
        total: int = 3,
        addressable: set[str] | None = None,
        failure: str | None = None,
        on_set=None,
    ) -> None:
        self.names = [f"Sat{index}" for index in range(total)]
        self.addressable_names = set(addressable or ())
        self.failure = failure
        self.on_set = on_set
        self.calls: list = []

    def satellite_addressability(self, topology):
        self.calls.append("status")
        return {
            "addressable": sorted(self.addressable_names),
            "total": len(self.names),
        }

    def set_satellites_addressable(self, topology, enabled, names=None):
        self.calls.append(("set", enabled, names))
        if self.failure == "network":
            raise NetworkOperationError("addressability failed")
        if self.failure == "unexpected":
            raise RuntimeError("controller exploded")
        targets = self.names if names is None else list(names)
        for name in targets:
            if name not in self.names:
                raise ValueError(f"Unknown satellite: {name}")
        for name in targets:
            if enabled:
                self.addressable_names.add(name)
            else:
                self.addressable_names.discard(name)
        if self.on_set is not None:
            self.on_set()
        return len(targets)


def _addressability_service(
    controller: FakeAddressabilityController | None = None,
    session: ProjectSession | None = None,
) -> tuple[AddressabilityService, FakeAddressabilityController]:
    """Return an addressability service with a fake controller."""
    session = session if session is not None else _loaded_session()
    controller = controller if controller is not None else FakeAddressabilityController()
    topology = TopologyService(session, FakeReader())
    return AddressabilityService(topology, controller), controller


def test_addressability_status_reports_sorted_names_and_counts() -> None:
    """Status lists the addressable satellites with count and total."""
    controller = FakeAddressabilityController(
        total=3,
        addressable={"Sat2", "Sat0"},
    )
    service, _ = _addressability_service(controller)

    assert service.status() == {
        "ok": True,
        "addressable": ["Sat0", "Sat2"],
        "count": 2,
        "total": 3,
        "routing_refresh_required": False,
    }

    service.topology.set_addressing_applied(True)
    assert service.status()["routing_refresh_required"] is True


def test_addressability_status_requires_a_project() -> None:
    """Status cannot be read before a project is loaded."""
    topology = TopologyService(ProjectSession(), FakeReader())
    service = AddressabilityService(topology, FakeAddressabilityController())

    with pytest.raises(APIError) as error:
        service.status()

    assert error.value.status_code == 404


def test_addressability_global_toggle_enables_and_disables_every_satellite() -> None:
    """The global toggle dispatches one unqualified controller call."""
    service, controller = _addressability_service()

    enabled = service.set_all(True)

    assert enabled == {
        "ok": True,
        "enabled": True,
        "updated": 3,
        "routing_refresh_required": False,
    }
    assert controller.calls == [("set", True, None)]
    assert service.topology.session.network_operation is False
    assert service.status()["count"] == 3
    assert controller.calls == [("set", True, None), "status"]

    disabled = service.set_all(False)

    assert disabled["enabled"] is False
    assert disabled["updated"] == 3
    assert controller.calls[-1] == ("set", False, None)
    assert service.status()["count"] == 0


def test_addressability_per_node_toggle_updates_one_satellite() -> None:
    """The per-node toggle reports the node and its new addressability."""
    service, controller = _addressability_service()

    result = service.set_one("Sat1", True)

    assert result == {
        "ok": True,
        "name": "Sat1",
        "addressable": True,
        "enabled": True,
        "updated": 1,
        "routing_refresh_required": False,
    }
    assert controller.calls == [("set", True, ["Sat1"])]
    assert service.topology.session.network_operation is False
    assert service.status()["addressable"] == ["Sat1"]


@pytest.mark.parametrize("name", ["Gnd100", "Satellite", "Sat", "Sat-1"])
def test_addressability_rejects_malformed_names_before_dispatch(name: str) -> None:
    """Only the core's satellite name form reaches the controller."""
    service, controller = _addressability_service()

    with pytest.raises(APIError) as error:
        service.set_one(name, True)

    assert error.value.status_code == 404
    assert controller.calls == []
    assert service.topology.session.network_operation is False


def test_addressability_missing_satellite_maps_to_404() -> None:
    """A satellite name the adapter cannot resolve is a client error."""
    service, controller = _addressability_service(FakeAddressabilityController(total=3))

    with pytest.raises(APIError) as error:
        service.set_one("Sat404", True)

    assert error.value.status_code == 404
    assert "Unknown satellite: Sat404" in error.value.message
    assert service.topology.session.network_operation is False


def test_addressability_rejects_an_in_flight_network_operation() -> None:
    """An addressability mutation cannot overlap routing/container work."""
    service, controller = _addressability_service()
    assert service.topology.session.begin_network_operation() is True
    try:
        with pytest.raises(APIError) as error:
            service.set_all(True)
    finally:
        service.topology.session.end_network_operation()

    assert error.value.status_code == 409
    assert "project operation" in error.value.message.lower()
    assert controller.calls == []


def test_addressability_rejects_a_project_changed_mid_operation() -> None:
    """A mutation must not report success on a replaced project."""
    session = _loaded_session()

    def replace_project() -> None:
        session.succeed(object(), "NewProject", "")

    controller = FakeAddressabilityController(on_set=replace_project)
    service, _ = _addressability_service(controller, session)

    with pytest.raises(APIError) as error:
        service.set_all(True)

    assert error.value.status_code == 409
    assert "Project changed" in error.value.message
    assert session.network_operation is False


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        ("network", "addressability failed"),
        ("unexpected", "Failed to update satellite addressability."),
    ],
)
def test_addressability_controller_failures_map_to_500(failure: str, message: str) -> None:
    """Controller failures are reported without leaking a traceback."""
    service, _ = _addressability_service(FakeAddressabilityController(failure=failure))

    with pytest.raises(APIError) as error:
        service.set_all(True)

    assert error.value.status_code == 500
    assert message in error.value.message
    assert service.topology.session.network_operation is False


def test_addressability_mutations_report_routing_refresh_after_the_update() -> None:
    """Both toggles report the addressing state after the change."""
    service, _ = _addressability_service()
    service.topology.set_addressing_applied(True)

    assert service.set_one("Sat1", True)["routing_refresh_required"] is True
    assert service.set_all(False)["routing_refresh_required"] is True
    assert service.status()["routing_refresh_required"] is True
