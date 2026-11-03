"""Contract tests for the real satgonetem topology adapter."""

from satgonetem_gui.adapters.satgonetem_topology import SatGoNetemTopologyAdapter
from satgonetem_gui.schemas import ProjectCreateRequest
from tests.factories import PROJECT_NAME, project_payload


def test_topology_adapter_round_trips_a_project(settings) -> None:
    """The adapter can build, inspect, serialize, and reload a 10x10 project."""
    adapter = SatGoNetemTopologyAdapter(settings)
    request = ProjectCreateRequest(**project_payload(PROJECT_NAME))

    result = adapter.build(request)
    topology = result.topology_manager

    assert result.project_name == PROJECT_NAME
    assert adapter.status(topology)["satellites"] == 100
    assert len(adapter.satellites(topology)) == 100
    assert len(adapter.ground_stations(topology)) == 1
    assert len(adapter.links(topology)) >= 200
    assert adapter.node_detail(topology, "Sat0")["type"] == "satellite"
    assert adapter.find_node(topology, "Sat0") is not None
    assert adapter.find_node(topology, "Missing") is None

    config = adapter.config(topology, "")
    assert config["name"] == PROJECT_NAME
    assert len(config["ground_objects_properties"][0]["stations"]) == 1

    content = adapter.save(topology)
    reloaded = adapter.load(content)
    assert reloaded.project_name == PROJECT_NAME
    assert adapter.status(reloaded.topology_manager)["satellites"] == 100


def test_display_name_strips_timestamp_suffixes(settings) -> None:
    """Runtime-state fallback names do not expose dependency timestamps."""
    from types import SimpleNamespace

    adapter = SatGoNetemTopologyAdapter(settings)
    topology = SimpleNamespace(
        simulation_property=None,
        project_name="Constellation_1793711838_1793711854",
    )

    assert adapter.display_name(topology) == "Constellation"


def test_adapter_maps_addressing_and_routing_failures(settings) -> None:
    """Negative dependency return codes become NetworkOperationError."""
    from types import SimpleNamespace

    import pytest

    from satgonetem_gui.services.ports import NetworkOperationError

    adapter = SatGoNetemTopologyAdapter(settings)
    addressing = SimpleNamespace(set_ip_addresses=lambda: -1.0)
    routing = SimpleNamespace(init_routing=lambda routing_method: -1.0)

    with pytest.raises(NetworkOperationError):
        adapter.apply_addressing(addressing)
    with pytest.raises(NetworkOperationError):
        adapter.init_routing(routing, "static")


def test_adapter_delete_and_start_failures(settings) -> None:
    """Delete/start return-code and state failures are mapped."""
    from types import SimpleNamespace

    import pytest

    from satgonetem_gui.services.ports import NetworkOperationError

    adapter = SatGoNetemTopologyAdapter(settings)
    deleting = SimpleNamespace(
        get_routing_initiated=lambda: True,
        delete_routing=lambda: -1.0,
    )
    starting = SimpleNamespace(
        start_gonetem=lambda: None,
        get_gonetem_status=lambda: False,
    )

    with pytest.raises(NetworkOperationError):
        adapter.delete_routing(deleting)
    with pytest.raises(NetworkOperationError):
        adapter.start_gonetem(starting)


def test_adapter_delete_is_idempotent_when_not_initialized(settings) -> None:
    """Deleting routing that was never applied is a no-op."""
    from types import SimpleNamespace

    adapter = SatGoNetemTopologyAdapter(settings)
    calls = []
    topology = SimpleNamespace(
        get_routing_initiated=lambda: False,
        delete_routing=lambda: calls.append("delete"),
    )

    adapter.delete_routing(topology)

    assert calls == []


def test_adapter_stop_does_not_fake_loaded_status(settings) -> None:
    """Stopping containers leaves status ownership to the project session."""
    from types import SimpleNamespace

    adapter = SatGoNetemTopologyAdapter(settings)
    calls = []
    topology = SimpleNamespace(
        stop_gonetem=lambda: calls.append("stop"),
        get_gonetem_status=lambda: False,
        set_status=lambda value: calls.append(("set_status", value)),
    )

    adapter.stop_gonetem(topology)

    assert calls == ["stop"]


def test_adapter_routing_status_omits_fake_addressing(settings) -> None:
    """Routing status leaves addressing state to the service layer."""
    from types import SimpleNamespace

    adapter = SatGoNetemTopologyAdapter(settings)
    topology = SimpleNamespace(
        get_gonetem_status=lambda: True,
        get_routing_initiated=lambda: False,
        routing="static",
    )

    status = adapter.routing_status(topology)

    assert status["gonetem_is_on"] is True
    assert "addressing_applied" not in status
