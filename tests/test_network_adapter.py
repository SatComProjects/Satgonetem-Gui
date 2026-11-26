"""Contract tests for the network, simulation, and connectivity adapter."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from satgonetem import connectivity as core_connectivity

from satgonetem_gui.adapters.network_adapter import NetworkAdapter
from satgonetem_gui.services.ports import NetworkOperationError
from tests.adapter_helpers import (
    AddressabilityTopology,
    FakeSatellite,
    connectivity_topology,
)


def test_adapter_maps_addressing_and_routing_failures() -> None:
    """Negative dependency return codes become NetworkOperationError."""
    adapter = NetworkAdapter()
    addressing = SimpleNamespace(set_ip_addresses=lambda: -1.0)
    routing = SimpleNamespace(init_routing=lambda routing_method: -1.0)

    with pytest.raises(NetworkOperationError):
        adapter.apply_addressing(addressing)
    with pytest.raises(NetworkOperationError):
        adapter.init_routing(routing, "static")


def test_adapter_maps_addressing_exceptions() -> None:
    """v0.3.2 raises when any node failed; expose it as a network error."""
    adapter = NetworkAdapter()

    def fail() -> None:
        raise RuntimeError("IPv4 assignment failed on 3 node(s)")

    topology = SimpleNamespace(set_ip_addresses=fail)

    with pytest.raises(NetworkOperationError, match="3 node"):
        adapter.apply_addressing(topology)


def test_adapter_delete_and_start_failures() -> None:
    """Delete/start return-code and state failures are mapped."""
    adapter = NetworkAdapter()
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


def test_adapter_start_cleans_up_partial_startup() -> None:
    """A failed start attempts to stop any containers it already created."""
    adapter = NetworkAdapter()
    calls = []

    def fail_start():
        calls.append("start")
        raise RuntimeError("launcher failed")

    topology = SimpleNamespace(
        start_gonetem=fail_start,
        stop_gonetem=lambda: calls.append("stop"),
        get_gonetem_status=lambda: False,
    )

    with pytest.raises(RuntimeError, match="launcher failed"):
        adapter.start_gonetem(topology)

    assert calls == ["start", "stop"]


def test_adapter_start_failure_after_status_check_still_cleans_up() -> None:
    """A start that reports no running containers also triggers cleanup."""
    adapter = NetworkAdapter()
    calls = []
    topology = SimpleNamespace(
        start_gonetem=lambda: calls.append("start"),
        stop_gonetem=lambda: calls.append("stop"),
        get_gonetem_status=lambda: False,
    )

    with pytest.raises(NetworkOperationError, match="failed to start"):
        adapter.start_gonetem(topology)

    assert calls == ["start", "stop"]


def test_adapter_delete_is_idempotent_when_not_initialized() -> None:
    """Deleting routing that was never applied is a no-op."""
    adapter = NetworkAdapter()
    calls = []
    topology = SimpleNamespace(
        get_routing_initiated=lambda: False,
        delete_routing=lambda: calls.append("delete"),
    )

    adapter.delete_routing(topology)

    assert calls == []


def test_adapter_stop_does_not_fake_loaded_status() -> None:
    """Stopping containers leaves status ownership to the project session."""
    adapter = NetworkAdapter()
    calls = []
    topology = SimpleNamespace(
        stop_gonetem=lambda: calls.append("stop"),
        get_gonetem_status=lambda: False,
        set_status=lambda value: calls.append(("set_status", value)),
    )

    adapter.stop_gonetem(topology)

    assert calls == ["stop"]


def test_adapter_routing_status_omits_fake_addressing() -> None:
    """Routing status leaves addressing state to the service layer."""
    adapter = NetworkAdapter()
    topology = SimpleNamespace(
        get_gonetem_status=lambda: True,
        get_routing_initiated=lambda: False,
        routing="static",
    )

    status = adapter.routing_status(topology)

    assert status["gonetem_is_on"] is True
    assert "addressing_applied" not in status


def test_adapter_simulation_controls_use_public_core_methods() -> None:
    """Each adapter operation calls the matching public core method."""
    adapter = NetworkAdapter()
    calls = []
    topology = SimpleNamespace(
        get_running=lambda: False,
        start=lambda: calls.append("start"),
        stop=lambda: calls.append("stop"),
        next_step=lambda: calls.append("step"),
        reset_simulation=lambda: calls.append("reset"),
        speed_up=lambda: calls.append("faster"),
        speed_down=lambda: calls.append("slower"),
    )

    assert adapter.simulation_running(topology) is False
    assert adapter.simulation_running(SimpleNamespace(get_running=lambda: True)) is True
    adapter.start_simulation(topology)
    adapter.stop_simulation(topology)
    adapter.step_simulation(topology)
    adapter.reset_simulation(topology)
    adapter.change_simulation_speed(topology, "faster")
    adapter.change_simulation_speed(topology, "slower")

    assert calls == ["start", "stop", "step", "reset", "faster", "slower"]

    with pytest.raises(ValueError, match="direction"):
        adapter.change_simulation_speed(topology, "sideways")


def test_adapter_seek_computes_the_absolute_step_time() -> None:
    """Seeking converts a step index into start_time plus whole ticks."""
    adapter = NetworkAdapter()
    targets = []
    start = datetime(2024, 1, 1)
    topology = SimpleNamespace(
        get_project_duration_in_timesteps=lambda: 120,
        start_time=start,
        update_time=5,
        move_to_time=targets.append,
    )

    adapter.seek_simulation(topology, 12)

    assert targets == [start + timedelta(seconds=60)]


@pytest.mark.parametrize("step", [-1, 121])
def test_adapter_seek_rejects_out_of_range_steps(step: int) -> None:
    """A target outside the project duration is rejected before moving."""
    adapter = NetworkAdapter()
    targets = []
    topology = SimpleNamespace(
        get_project_duration_in_timesteps=lambda: 120,
        start_time=datetime(2024, 1, 1),
        update_time=5,
        move_to_time=targets.append,
    )

    with pytest.raises(ValueError, match="outside"):
        adapter.seek_simulation(topology, step)

    assert targets == []


def test_adapter_addressability_status_is_sorted_with_total() -> None:
    """Status reports sorted addressable names and the satellite total."""
    adapter = NetworkAdapter()
    topology = AddressabilityTopology(
        [
            FakeSatellite("Sat10", 10, True),
            FakeSatellite("Sat2", 2, True),
            FakeSatellite("Sat0", 0, False),
        ]
    )

    assert adapter.satellite_addressability(topology) == {
        "addressable": ["Sat10", "Sat2"],
        "total": 3,
    }


def test_adapter_enables_satellites_through_the_core_method() -> None:
    """Enabling delegates to the public bulk core operation."""
    adapter = NetworkAdapter()
    first = FakeSatellite("Sat0", 0)
    second = FakeSatellite("Sat1", 1)
    topology = AddressabilityTopology([first, second])

    assert adapter.set_satellites_addressable(topology, True, None) == 2

    assert topology.enable_calls == [[first, second]]
    assert first.addressable is True
    assert second.addressable is True


def test_adapter_enables_only_requested_satellites() -> None:
    """A targeted enable passes exactly the matching satellites."""
    adapter = NetworkAdapter()
    first = FakeSatellite("Sat0", 0)
    second = FakeSatellite("Sat1", 1)
    topology = AddressabilityTopology([first, second])

    assert adapter.set_satellites_addressable(topology, True, ["Sat1"]) == 1

    assert topology.enable_calls == [[second]]
    assert first.addressable is False
    assert second.addressable is True


def test_adapter_disables_satellites_through_each_public_node() -> None:
    """Disabling flips each target directly and skips the bulk enable call."""
    adapter = NetworkAdapter()
    first = FakeSatellite("Sat0", 0, True)
    second = FakeSatellite("Sat1", 1, True)
    topology = AddressabilityTopology([first, second])

    assert adapter.set_satellites_addressable(topology, False, ["Sat1"]) == 1

    assert topology.enable_calls == []
    assert first.addressable is True
    assert second.addressable is False
    assert second.address_calls == [False]

    assert adapter.set_satellites_addressable(topology, False, None) == 2
    assert first.addressable is False
    assert second.addressable is False


def test_adapter_rejects_unknown_satellites_before_any_change() -> None:
    """An unknown name fails the whole request without partial updates."""
    adapter = NetworkAdapter()
    first = FakeSatellite("Sat0", 0)
    topology = AddressabilityTopology([first])

    with pytest.raises(ValueError, match="Unknown satellite: Sat404"):
        adapter.set_satellites_addressable(topology, True, ["Sat404"])
    with pytest.raises(ValueError, match="Unknown satellite: Sat400"):
        adapter.set_satellites_addressable(topology, True, ["Sat0", "Sat400"])

    assert first.addressable is False
    assert topology.enable_calls == []


def test_adapter_addressability_with_no_targets_is_a_noop() -> None:
    """An empty satellite set or selection updates nothing."""
    adapter = NetworkAdapter()

    assert adapter.set_satellites_addressable(AddressabilityTopology([]), True) == 0

    topology = AddressabilityTopology([FakeSatellite("Sat0", 0)])
    assert adapter.set_satellites_addressable(topology, True, []) == 0
    assert topology.enable_calls == []


def test_connectivity_nodes_default_to_ground_first_then_satellites() -> None:
    """All addressable endpoints are returned in deterministic id order."""
    adapter = NetworkAdapter()

    nodes = adapter.resolve_connectivity_nodes(connectivity_topology(), None)

    assert nodes == ["Gnd5", "Gnd10", "Sat3", "Sat12"]


def test_connectivity_nodes_preserve_the_requested_order_without_duplicates() -> None:
    """A selected subset is validated, deduplicated, and kept in request order."""
    adapter = NetworkAdapter()

    nodes = adapter.resolve_connectivity_nodes(
        connectivity_topology(),
        ["Sat12", "Gnd10", "Sat12"],
    )

    assert nodes == ["Sat12", "Gnd10"]


@pytest.mark.parametrize("name", ["Sat7", "Sat9", "Gnd8", "Missing"])
def test_connectivity_nodes_reject_non_addressable_endpoints(name: str) -> None:
    """Unaddressable satellites, stations without interfaces, and unknown names fail."""
    adapter = NetworkAdapter()

    with pytest.raises(
        ValueError,
        match=f"Node is not an addressable traffic endpoint: {name}",
    ):
        adapter.resolve_connectivity_nodes(
            connectivity_topology(),
            ["Sat3", name],
        )


@pytest.mark.parametrize(
    "names",
    [None, [], ["Sat3"], ["Sat3", "Sat3"]],
)
def test_connectivity_nodes_require_at_least_two(names) -> None:
    """A matrix needs two distinct addressable endpoints."""
    adapter = NetworkAdapter()
    topology = connectivity_topology()
    if names is None:
        topology.ground_stations = {}
        topology.satellites = {3: topology.satellites[3]}

    with pytest.raises(
        ValueError,
        match="At least two addressable nodes are required",
    ):
        adapter.resolve_connectivity_nodes(topology, names)


def test_connectivity_matrix_uses_core_config_and_returns_named_results(
    monkeypatch,
) -> None:
    """The adapter resolves objects, pins the ping config, and shapes results."""
    captured = {}

    class FakeMatrix:
        def to_dict(self):
            return {
                "summary": {"pairs": 2, "reachable": 1, "unreachable": 1},
                "results": [
                    {
                        "source": "Sat3",
                        "destination": "Gnd5",
                        "reachable": True,
                    }
                ],
            }

    def fake_build(nodes, **kwargs):
        captured["nodes"] = list(nodes)
        captured.update(kwargs)
        return FakeMatrix()

    monkeypatch.setattr(
        core_connectivity,
        "build_connectivity_matrix",
        fake_build,
    )
    adapter = NetworkAdapter()
    topology = connectivity_topology()

    result = adapter.run_connectivity_matrix(
        topology,
        ["Sat3", "Gnd5"],
        ping_count=3,
        max_workers=4,
        flow_timeout_seconds=2.5,
    )

    assert [node.name for node in captured["nodes"]] == ["Sat3", "Gnd5"]
    config = captured["config"]
    assert config.count == 3
    assert config.interval_sec == 0.01
    assert config.preload == 1
    assert config.packet_size == 64
    assert captured["max_workers"] == 4
    assert captured["flow_timeout_sec"] == 2.5
    assert result["nodes"] == ["Sat3", "Gnd5"]
    assert result["summary"]["pairs"] == 2
    assert result["results"][0]["source"] == "Sat3"


def test_connectivity_matrix_translates_core_failures(monkeypatch) -> None:
    """An unexpected core failure becomes a safe runtime error for the job."""
    monkeypatch.setattr(
        core_connectivity,
        "build_connectivity_matrix",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("scheduler exploded")),
    )
    adapter = NetworkAdapter()

    with pytest.raises(RuntimeError, match="Connectivity check failed"):
        adapter.run_connectivity_matrix(
            connectivity_topology(),
            ["Sat3", "Gnd5"],
            ping_count=1,
            max_workers=1,
            flow_timeout_seconds=1.0,
        )
