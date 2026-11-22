"""Contract tests for the real satgonetem topology adapter."""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from satgonetem_gui.adapters.satgonetem_topology import SatGoNetemTopologyAdapter
from satgonetem_gui.schemas import ProjectCreateRequest
from satgonetem_gui.services.ports import NetworkOperationError
from tests.factories import PROJECT_NAME, project_payload


def _traffic_endpoint(
    name: str,
    node_id: int,
    *,
    interfaces: int = 1,
    city: str | None = None,
    addressable: bool | None = None,
) -> SimpleNamespace:
    """Build a node stand-in with the fields traffic_nodes reads."""
    node = SimpleNamespace(
        name=name,
        id=node_id,
        interfaces=[object()] * interfaces,
    )
    if city is not None:
        node.city = city
    if addressable is not None:
        node.is_addressable = lambda: addressable
    return node


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


def test_traffic_nodes_filters_and_orders_endpoints(settings) -> None:
    """Only addressable endpoints with interfaces are returned, ground stations first."""
    adapter = SatGoNetemTopologyAdapter(settings)
    topology = SimpleNamespace(
        ground_stations={
            10: _traffic_endpoint("Gnd10", 10, city="Oslo"),
            5: _traffic_endpoint("Gnd5", 5),
            8: _traffic_endpoint("Gnd8", 8, city="Rome", interfaces=0),
        },
        satellites={
            12: _traffic_endpoint("Sat12", 12, addressable=True),
            3: _traffic_endpoint("Sat3", 3, addressable=True, interfaces=2),
            7: _traffic_endpoint("Sat7", 7, addressable=False),
            9: _traffic_endpoint("Sat9", 9, addressable=True, interfaces=0),
        },
    )

    assert adapter.traffic_nodes(topology) == [
        {"name": "Gnd5", "type": "ground_station", "label": "Gnd5"},
        {
            "name": "Gnd10",
            "type": "ground_station",
            "label": "Gnd10 (Oslo)",
        },
        {"name": "Sat3", "type": "satellite", "label": "Sat3"},
        {"name": "Sat12", "type": "satellite", "label": "Sat12"},
    ]


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


def test_adapter_maps_addressing_exceptions(settings) -> None:
    """v0.3.2 raises when any node failed; expose it as a network error."""
    adapter = SatGoNetemTopologyAdapter(settings)

    def fail() -> None:
        raise RuntimeError("IPv4 assignment failed on 3 node(s)")

    topology = SimpleNamespace(set_ip_addresses=fail)

    with pytest.raises(NetworkOperationError, match="3 node"):
        adapter.apply_addressing(topology)


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


def test_adapter_start_cleans_up_partial_startup(settings) -> None:
    """A failed start attempts to stop any containers it already created."""
    adapter = SatGoNetemTopologyAdapter(settings)
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


def test_adapter_start_failure_after_status_check_still_cleans_up(settings) -> None:
    """A start that reports no running containers also triggers cleanup."""
    adapter = SatGoNetemTopologyAdapter(settings)
    calls = []
    topology = SimpleNamespace(
        start_gonetem=lambda: calls.append("start"),
        stop_gonetem=lambda: calls.append("stop"),
        get_gonetem_status=lambda: False,
    )

    with pytest.raises(NetworkOperationError, match="failed to start"):
        adapter.start_gonetem(topology)

    assert calls == ["start", "stop"]


def test_node_detail_uses_the_core_node_type_not_the_name(settings) -> None:
    """A ground station named with a Sat prefix is still classified as ground."""
    adapter = SatGoNetemTopologyAdapter(settings)
    node = SimpleNamespace(
        name="SatGround",
        type="GroundStation",
        id=7,
        interfaces=[],
        position={"latitude": 1.0, "longitude": 2.0, "altitude": 0.1},
        loopback=SimpleNamespace(ipv4="10.0.0.1"),
        get_routing_table=lambda: [],
        city="Berlin",
    )
    topology = SimpleNamespace(
        get_node_by_name=lambda _name: node,
        _sync_node_positions=lambda: None,
    )

    detail = adapter.node_detail(topology, "SatGround")

    assert detail is not None
    assert detail["type"] == "ground_station"
    assert detail["city"] == "Berlin"
    assert "default_qos_is_on" not in detail


def test_adapter_writes_topology_atomically(settings, tmp_path) -> None:
    """A failed serialization leaves the previous target intact."""
    adapter = SatGoNetemTopologyAdapter(settings)
    target = tmp_path / "project.json"
    target.write_text("old", encoding="utf-8")

    class FailingTopology:
        def to_file(self, path):
            Path(path).write_text("partial", encoding="utf-8")
            raise RuntimeError("write failed")

    with pytest.raises(RuntimeError, match="write failed"):
        adapter._write_topology_atomically(FailingTopology(), target)

    assert target.read_text(encoding="utf-8") == "old"
    assert list(tmp_path.glob("*.tmp")) == []


def test_position_sync_hook_change_is_reported(settings) -> None:
    """A core rename of the private position hook fails loudly."""
    from satgonetem_gui.adapters.satgonetem_topology import (
        SatGoNetemTopologyAdapter as Adapter,
    )

    with pytest.raises(RuntimeError, match="_sync_node_positions"):
        Adapter._sync_positions(SimpleNamespace())


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


def _ground_data_file(topology) -> Path:
    """Return the first ground object's data file for a built topology."""
    ground = topology.simulation_property.ground_objects_properties[0]
    return Path(ground.data_file)


def test_build_writes_inline_stations_under_save_root(settings) -> None:
    """Inline station CSV files live in the managed save-root directory."""
    adapter = SatGoNetemTopologyAdapter(settings)
    result = adapter.build(ProjectCreateRequest(**project_payload()))

    data_file = _ground_data_file(result.topology_manager)

    assert data_file.parent == settings.save_root / ".satgonetem" / "ground_stations"
    assert data_file.resolve().is_relative_to(settings.save_root.resolve())
    assert data_file.is_file()


def test_config_and_save_fail_loudly_when_station_file_is_missing(settings) -> None:
    """A deleted station file raises instead of silently returning no stations."""
    adapter = SatGoNetemTopologyAdapter(settings)
    result = adapter.build(ProjectCreateRequest(**project_payload()))
    _ground_data_file(result.topology_manager).unlink()

    with pytest.raises(ValueError, match="Could not read ground station file"):
        adapter.config(result.topology_manager, "")
    with pytest.raises(ValueError, match="Ground station data file is unavailable"):
        adapter.save(result.topology_manager)


def test_build_rejects_comma_in_station_name_before_core(settings) -> None:
    """Custom station names with commas produce a clear adapter error."""
    adapter = SatGoNetemTopologyAdapter(settings)
    payload = project_payload()
    grounds = json.loads(payload["ground_objects_properties_json"])
    grounds[0]["stations"][0]["name"] = "Berlin, DE"
    payload["ground_objects_properties_json"] = json.dumps(grounds)

    with pytest.raises(ValueError, match="must not contain commas, quotes, or newlines"):
        adapter.build(ProjectCreateRequest(**payload))


def test_build_cleans_up_station_files_when_build_fails(settings) -> None:
    """A failed build does not leave managed station files behind."""
    adapter = SatGoNetemTopologyAdapter(settings)
    payload = project_payload(save_path="../outside.json")

    with pytest.raises(ValueError):
        adapter.build(ProjectCreateRequest(**payload))

    stable_dir = settings.save_root / ".satgonetem" / "ground_stations"
    assert list(stable_dir.glob("*.csv")) == []


def test_cleanup_ground_files_keeps_only_referenced_files(settings) -> None:
    """Files left by earlier builds are removed after a topology is installed."""
    adapter = SatGoNetemTopologyAdapter(settings)
    result = adapter.build(ProjectCreateRequest(**project_payload()))
    referenced = _ground_data_file(result.topology_manager)
    stale = referenced.parent / "stale-stations.csv"
    stale.write_text("0,Oslo,59.91,10.75,0.01\n", encoding="utf-8")

    adapter.cleanup_ground_files(result.topology_manager)

    assert referenced.is_file()
    assert not stale.exists()


def test_config_and_save_reject_external_data_files(settings, tmp_path: Path) -> None:
    """Ground files outside the packaged and save roots cannot be read or saved."""
    adapter = SatGoNetemTopologyAdapter(settings)
    result = adapter.build(ProjectCreateRequest(**project_payload()))
    external = tmp_path / "external-stations.csv"
    external.write_text("0,Oslo,59.91,10.75,0.01\n", encoding="utf-8")
    result.topology_manager.simulation_property.ground_objects_properties[0].data_file = str(
        external
    )

    with pytest.raises(ValueError, match="Could not read ground station file"):
        adapter.config(result.topology_manager, "")
    with pytest.raises(ValueError, match="Ground station data file is unavailable"):
        adapter.save(result.topology_manager)


def test_load_accepts_embedded_files_from_another_machine(settings) -> None:
    """A backup whose original data_file is outside the roots still loads."""
    adapter = SatGoNetemTopologyAdapter(settings)
    result = adapter.build(ProjectCreateRequest(**project_payload()))
    original = _ground_data_file(result.topology_manager)
    document = json.loads(adapter.save(result.topology_manager))
    original_key = str(original)
    outside_key = "/old/machine/ground_stations.csv"
    document["simulation_property"]["ground_objects_properties"][0]["data_file"] = outside_key
    document["ground_files"][outside_key] = document["ground_files"].pop(original_key)

    loaded = adapter.load(json.dumps(document))

    config = adapter.config(loaded.topology_manager, "")
    assert config["ground_objects_properties"][0]["stations"][0]["name"] == "Berlin"
    migrated = _ground_data_file(loaded.topology_manager)
    assert migrated.resolve().is_relative_to(settings.save_root.resolve())
    assert migrated.is_file()


def test_load_migrates_restored_files_and_backups_remain_restorable(settings) -> None:
    """Loaded projects keep stations in the save root and round-trip backups."""
    adapter = SatGoNetemTopologyAdapter(settings)
    result = adapter.build(ProjectCreateRequest(**project_payload()))
    original = _ground_data_file(result.topology_manager)
    content = adapter.save(result.topology_manager)
    original.unlink()

    restore_dirs_before = {
        path for path in Path(tempfile.gettempdir()).glob("*_ground_files_*") if path.is_dir()
    }
    loaded = adapter.load(content)
    restore_dirs_after = {
        path for path in Path(tempfile.gettempdir()).glob("*_ground_files_*") if path.is_dir()
    }

    migrated = _ground_data_file(loaded.topology_manager)
    assert restore_dirs_after == restore_dirs_before
    assert migrated.parent == settings.save_root / ".satgonetem" / "ground_stations"
    assert migrated.is_file()
    assert migrated != original
    config = adapter.config(loaded.topology_manager, "")
    assert config["ground_objects_properties"][0]["stations"][0]["name"] == "Berlin"

    backup = adapter.save(loaded.topology_manager)
    migrated.unlink()
    reloaded = adapter.load(backup)
    config = adapter.config(reloaded.topology_manager, "")
    assert config["ground_objects_properties"][0]["stations"][0]["name"] == "Berlin"


def _simulation_topology(**overrides) -> SimpleNamespace:
    """Build a topology stand-in exposing the public simulation API."""
    values = {
        "get_topology_summary": lambda: {
            "satellites": 1,
            "ground_stations": 0,
            "links": 0,
        },
        "get_current_time": lambda: None,
        "get_status": lambda: True,
        "get_gonetem_status": lambda: False,
        "get_running": lambda: False,
        "get_current_time_step": lambda: 0,
        "get_project_duration_in_timesteps": lambda: 120,
        "update_factor": 1.0,
        "get_last_simulation_error": lambda: None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_adapter_simulation_controls_use_public_core_methods(settings) -> None:
    """Each adapter operation calls the matching public core method."""
    adapter = SatGoNetemTopologyAdapter(settings)
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


def test_adapter_seek_computes_the_absolute_step_time(settings) -> None:
    """Seeking converts a step index into start_time plus whole ticks."""
    adapter = SatGoNetemTopologyAdapter(settings)
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
def test_adapter_seek_rejects_out_of_range_steps(settings, step: int) -> None:
    """A target outside the project duration is rejected before moving."""
    adapter = SatGoNetemTopologyAdapter(settings)
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


def test_adapter_status_includes_simulation_transport_metadata(settings) -> None:
    """Status exposes total steps, playback rate, and the last tick error."""
    adapter = SatGoNetemTopologyAdapter(settings)
    topology = _simulation_topology(
        update_factor=0.5,
        get_last_simulation_error=lambda: RuntimeError("tick failed"),
    )

    status = adapter.status(topology)

    assert status["total_steps"] == 120
    assert status["simulation_rate"] == 2.0
    assert status["last_simulation_error"] == "RuntimeError: tick failed"


def test_adapter_status_degrades_when_transport_metadata_is_unavailable(
    settings,
) -> None:
    """A missing core value must not break the dashboard status read."""

    def fail() -> None:
        raise RuntimeError("core value unavailable")

    adapter = SatGoNetemTopologyAdapter(settings)
    topology = _simulation_topology(
        get_project_duration_in_timesteps=fail,
        update_factor=0,
        get_last_simulation_error=fail,
    )

    status = adapter.status(topology)

    assert status["satellites"] == 1
    assert status["total_steps"] is None
    assert status["simulation_rate"] == 1.0
    assert status["last_simulation_error"] is None


def test_adapter_status_truncates_long_simulation_errors(settings) -> None:
    """A verbose tick error is summarized without a traceback."""
    adapter = SatGoNetemTopologyAdapter(settings)
    topology = _simulation_topology(get_last_simulation_error=lambda: RuntimeError("x" * 600))

    message = adapter.status(topology)["last_simulation_error"]

    assert message is not None
    assert message.startswith("RuntimeError: ")
    assert len(message) == 500


class _FakeSatellite:
    """Satellite stand-in exposing the public addressability API."""

    def __init__(self, name: str, satellite_id: int, addressable: bool = False) -> None:
        self.name = name
        self.id = satellite_id
        self.addressable = addressable
        self.address_calls: list[bool] = []

    def is_addressable(self) -> bool:
        return self.addressable

    def set_addressable(self, status: bool) -> None:
        self.address_calls.append(status)
        self.addressable = status


class _AddressabilityTopology:
    """Topology stand-in recording public satellite enable calls."""

    def __init__(self, satellites: list[_FakeSatellite]) -> None:
        self.satellites = {satellite.id: satellite for satellite in satellites}
        self.enable_calls: list[list[_FakeSatellite]] = []

    def set_addressable_satellites(self, satellites) -> None:
        targets = list(satellites)
        self.enable_calls.append(targets)
        for satellite in targets:
            satellite.set_addressable(True)


def test_adapter_addressability_status_is_sorted_with_total(settings) -> None:
    """Status reports sorted addressable names and the satellite total."""
    adapter = SatGoNetemTopologyAdapter(settings)
    topology = _AddressabilityTopology(
        [
            _FakeSatellite("Sat10", 10, True),
            _FakeSatellite("Sat2", 2, True),
            _FakeSatellite("Sat0", 0, False),
        ]
    )

    assert adapter.satellite_addressability(topology) == {
        "addressable": ["Sat10", "Sat2"],
        "total": 3,
    }


def test_adapter_enables_satellites_through_the_core_method(settings) -> None:
    """Enabling delegates to the public bulk core operation."""
    adapter = SatGoNetemTopologyAdapter(settings)
    first = _FakeSatellite("Sat0", 0)
    second = _FakeSatellite("Sat1", 1)
    topology = _AddressabilityTopology([first, second])

    assert adapter.set_satellites_addressable(topology, True, None) == 2

    assert topology.enable_calls == [[first, second]]
    assert first.addressable is True
    assert second.addressable is True


def test_adapter_enables_only_requested_satellites(settings) -> None:
    """A targeted enable passes exactly the matching satellites."""
    adapter = SatGoNetemTopologyAdapter(settings)
    first = _FakeSatellite("Sat0", 0)
    second = _FakeSatellite("Sat1", 1)
    topology = _AddressabilityTopology([first, second])

    assert adapter.set_satellites_addressable(topology, True, ["Sat1"]) == 1

    assert topology.enable_calls == [[second]]
    assert first.addressable is False
    assert second.addressable is True


def test_adapter_disables_satellites_through_each_public_node(settings) -> None:
    """Disabling flips each target directly and skips the bulk enable call."""
    adapter = SatGoNetemTopologyAdapter(settings)
    first = _FakeSatellite("Sat0", 0, True)
    second = _FakeSatellite("Sat1", 1, True)
    topology = _AddressabilityTopology([first, second])

    assert adapter.set_satellites_addressable(topology, False, ["Sat1"]) == 1

    assert topology.enable_calls == []
    assert first.addressable is True
    assert second.addressable is False
    assert second.address_calls == [False]

    assert adapter.set_satellites_addressable(topology, False, None) == 2
    assert first.addressable is False
    assert second.addressable is False


def test_adapter_rejects_unknown_satellites_before_any_change(settings) -> None:
    """An unknown name fails the whole request without partial updates."""
    adapter = SatGoNetemTopologyAdapter(settings)
    first = _FakeSatellite("Sat0", 0)
    topology = _AddressabilityTopology([first])

    with pytest.raises(ValueError, match="Unknown satellite: Sat404"):
        adapter.set_satellites_addressable(topology, True, ["Sat404"])
    with pytest.raises(ValueError, match="Unknown satellite: Sat400"):
        adapter.set_satellites_addressable(topology, True, ["Sat0", "Sat400"])

    assert first.addressable is False
    assert topology.enable_calls == []


def test_adapter_addressability_with_no_targets_is_a_noop(settings) -> None:
    """An empty satellite set or selection updates nothing."""
    adapter = SatGoNetemTopologyAdapter(settings)

    assert adapter.set_satellites_addressable(_AddressabilityTopology([]), True) == 0

    topology = _AddressabilityTopology([_FakeSatellite("Sat0", 0)])
    assert adapter.set_satellites_addressable(topology, True, []) == 0
    assert topology.enable_calls == []


def test_node_detail_exposes_addressability_for_satellites_only(settings) -> None:
    """Satellite details carry the toggle state; ground stations do not."""
    adapter = SatGoNetemTopologyAdapter(settings)
    satellite = SimpleNamespace(
        name="Sat0",
        type="Satellite",
        id=0,
        interfaces=[],
        position={"latitude": 1.0, "longitude": 2.0, "altitude": 550.0},
        loopback=SimpleNamespace(ipv4="10.0.0.1"),
        get_routing_table=lambda: [],
        is_addressable=lambda: True,
    )
    ground = SimpleNamespace(
        name="Gnd0",
        type="GroundStation",
        id=1,
        interfaces=[],
        position={"latitude": 3.0, "longitude": 4.0, "altitude": 0.1},
        loopback=SimpleNamespace(ipv4="10.0.0.2"),
        get_routing_table=lambda: [],
        city="Berlin",
    )
    nodes = {"Sat0": satellite, "Gnd0": ground}
    topology = SimpleNamespace(
        get_node_by_name=nodes.get,
        _sync_node_positions=lambda: None,
    )

    assert adapter.node_detail(topology, "Sat0")["addressable"] is True
    assert "addressable" not in adapter.node_detail(topology, "Gnd0")


def _path_node(name: str, node_id: int) -> SimpleNamespace:
    """Build a node stand-in with the identity fields the path reads."""
    return SimpleNamespace(name=name, id=node_id)


def _path_topology(
    nodes: list[SimpleNamespace],
    path: list[SimpleNamespace],
    edges: dict,
    *,
    initiated: bool = False,
    routing: str = "static",
    preference: str | None = "latency_no_preference",
) -> SimpleNamespace:
    """Build a topology stand-in exposing the public routing-path surface."""
    by_name = {node.name: node for node in nodes}
    return SimpleNamespace(
        routing=routing,
        preference=preference,
        get_node_by_name=by_name.get,
        get_current_graph=lambda: edges,
        get_path_between_nodes=lambda source, target: path,
        get_routing_initiated=lambda: initiated,
    )


def test_routing_path_builds_hops_with_distance_and_delay(settings) -> None:
    """Consecutive nodes become hops with propagation delay and running totals."""
    adapter = SatGoNetemTopologyAdapter(settings)
    ground = _path_node("Gnd10", 10)
    sat0 = _path_node("Sat0", 0)
    sat1 = _path_node("Sat1", 1)
    edges = {
        10: {
            0: {
                "type": "GroundStationLink",
                "distance_km": 1500.0,
            }
        },
        0: {
            1: {
                "type": "InterSatelliteLink",
                "direction": "UP",
                "distance_km": 3000.25,
            }
        },
    }
    topology = _path_topology([ground, sat0, sat1], [ground, sat0, sat1], edges, initiated=True)

    result = adapter.routing_path(topology, "Gnd10", "Sat1")

    assert result["src"] == "Gnd10"
    assert result["dst"] == "Sat1"
    assert result["found"] is True
    assert result["node_count"] == 3
    assert result["path_source"] == "routing_graph"
    assert "not the live forwarding table" in result["note"]
    assert result["routing_method"] == "static"
    assert result["routing_initiated"] is True
    assert result["preference"] == "latency_no_preference"
    assert result["hops"] == [
        {
            "source": "Gnd10",
            "target": "Sat0",
            "type": "GroundStationLink",
            "direction": None,
            "distance_km": 1500.0,
            "delay_ms": 5.0,
            "cumulative_distance_km": 1500.0,
            "cumulative_delay_ms": 5.0,
        },
        {
            "source": "Sat0",
            "target": "Sat1",
            "type": "InterSatelliteLink",
            "direction": "UP",
            "distance_km": 3000.25,
            "delay_ms": pytest.approx(10.01, abs=0.01),
            "cumulative_distance_km": 4500.25,
            "cumulative_delay_ms": pytest.approx(15.01, abs=0.01),
        },
    ]
    assert result["total_distance_km"] == 4500.25
    assert result["total_delay_ms"] == pytest.approx(15.01, abs=0.01)


def test_routing_path_without_a_route_returns_an_empty_result(settings) -> None:
    """No path is a valid diagnostic answer, not an error."""
    adapter = SatGoNetemTopologyAdapter(settings)
    sat0 = _path_node("Sat0", 0)
    topology = _path_topology([sat0, _path_node("Sat1", 1)], [], {0: {}}, routing="dynamic-ospf")

    result = adapter.routing_path(topology, "Sat0", "Sat1")

    assert result["found"] is False
    assert result["hops"] == []
    assert result["node_count"] == 0
    assert result["total_distance_km"] == 0.0
    assert result["total_delay_ms"] == 0.0
    assert result["routing_method"] == "dynamic-ospf"
    assert result["routing_initiated"] is False
    assert result["preference"] == "latency_no_preference"
    assert result["path_source"] == "routing_graph"
    assert "not the live forwarding table" in result["note"]


def test_routing_path_rejects_identical_endpoints(settings) -> None:
    """The same node twice cannot form a path."""
    adapter = SatGoNetemTopologyAdapter(settings)
    sat0 = _path_node("Sat0", 0)
    topology = _path_topology([sat0], [sat0], {0: {}})

    with pytest.raises(ValueError, match="differ"):
        adapter.routing_path(topology, "Sat0", "Sat0")


def test_routing_path_rejects_an_unknown_node(settings) -> None:
    """An unknown endpoint is reported before the graph is read."""
    adapter = SatGoNetemTopologyAdapter(settings)
    topology = _path_topology([_path_node("Sat0", 0)], [], {0: {}})

    with pytest.raises(ValueError, match="Node not found: Missing"):
        adapter.routing_path(topology, "Sat0", "Missing")


def test_routing_path_rejects_a_path_missing_from_the_graph(settings) -> None:
    """A path whose edge vanished is a contract error, not a silent skip."""
    adapter = SatGoNetemTopologyAdapter(settings)
    sat0 = _path_node("Sat0", 0)
    sat1 = _path_node("Sat1", 1)
    topology = _path_topology([sat0, sat1], [sat0, sat1], {})

    with pytest.raises(ValueError, match="no longer present"):
        adapter.routing_path(topology, "Sat0", "Sat1")


def test_links_include_delay_capacity_and_active_state(settings) -> None:
    """The link payload carries the metrics needed by the inspector."""
    adapter = SatGoNetemTopologyAdapter(settings)
    source = SimpleNamespace(name="Gnd100")
    target = SimpleNamespace(name="Sat0")
    topology = SimpleNamespace(
        links={
            "Gnd100-Sat0": SimpleNamespace(
                source=source,
                target=target,
                type="GroundStationLink",
                direction="",
                distance=1_500_000.0,
                is_active=False,
                get_capacity=lambda: 100_000,
            )
        }
    )

    links = adapter.links(topology)

    assert links == [
        {
            "src": "Gnd100",
            "dst": "Sat0",
            "type": "GroundStationLink",
            "direction": "",
            "distance_km": 1500.0,
            "delay_ms": 5.0,
            "capacity_kbps": 100000,
            "is_active": False,
        }
    ]


def _usage_link(src: str, dst: str, capacity_kbps: int) -> SimpleNamespace:
    """Build a link stand-in exposing only the capacity read."""
    return SimpleNamespace(
        source=SimpleNamespace(name=src),
        target=SimpleNamespace(name=dst),
        get_capacity=lambda: capacity_kbps,
    )


def _usage_topology(
    *,
    gonetem: bool = True,
    links: list[SimpleNamespace] | None = None,
    usage: list[dict] | None = None,
    failure: Exception | None = None,
) -> SimpleNamespace:
    """Build a topology stand-in for the public link-usage query."""
    links = links or []
    by_key = {f"{link.source.name}-{link.target.name}": link for link in links}

    def get_usage() -> list[dict]:
        if failure is not None:
            raise failure
        return usage or []

    return SimpleNamespace(
        get_gonetem_status=lambda: gonetem,
        get_all_links_usage=get_usage,
        links=by_key,
    )


def test_link_usage_is_unavailable_when_containers_are_stopped(settings) -> None:
    """Stopped containers are reported as an empty, unavailable sample."""
    adapter = SatGoNetemTopologyAdapter(settings)

    result = adapter.link_usage(_usage_topology(gonetem=False))

    assert result == {
        "available": False,
        "sampled_at": None,
        "links": [],
        "note": "GoNetEm containers are stopped; link usage is unavailable.",
    }
    assert "container" in result["note"].lower()


def test_link_usage_normalizes_values_capacities_and_utilization(settings) -> None:
    """Bits per second are clamped and mapped to link capacities."""
    adapter = SatGoNetemTopologyAdapter(settings)
    topology = _usage_topology(
        links=[
            _usage_link("Sat0", "Sat1", 100_000),
            _usage_link("Sat1", "Gnd0", 0),
        ],
        usage=[
            {
                "src": "Sat0",
                "dst": "Sat1",
                "value": 25_000_000,
                "type": "InterSatelliteLink",
            },
            {
                "src": "Sat1",
                "dst": "Gnd0",
                "value": -5,
                "type": "GroundStationLink",
            },
            {"src": "Sat1", "dst": "Sat2", "value": "unknown", "type": None},
        ],
    )

    result = adapter.link_usage(topology)

    assert result["available"] is True
    assert result["note"] is None
    assert datetime.fromisoformat(result["sampled_at"]).tzinfo is not None
    entries = {(entry["src"], entry["dst"]): entry for entry in result["links"]}
    assert entries[("Sat0", "Sat1")] == {
        "src": "Sat0",
        "dst": "Sat1",
        "type": "InterSatelliteLink",
        "value_bps": 25_000_000,
        "capacity_kbps": 100_000,
        "utilization": 0.25,
    }
    assert entries[("Sat1", "Gnd0")] == {
        "src": "Sat1",
        "dst": "Gnd0",
        "type": "GroundStationLink",
        "value_bps": 0,
        "capacity_kbps": None,
        "utilization": None,
    }
    assert entries[("Sat1", "Sat2")]["capacity_kbps"] is None
    assert entries[("Sat1", "Sat2")]["utilization"] is None
    assert entries[("Sat1", "Sat2")]["type"] is None


def test_link_usage_clamps_utilization_to_one(settings) -> None:
    """Usage above the nominal capacity is reported as saturated."""
    adapter = SatGoNetemTopologyAdapter(settings)
    topology = _usage_topology(
        links=[_usage_link("Sat0", "Sat1", 1_000)],
        usage=[{"src": "Sat0", "dst": "Sat1", "value": 5_000_000}],
    )

    entry = adapter.link_usage(topology)["links"][0]

    assert entry["value_bps"] == 5_000_000
    assert entry["capacity_kbps"] == 1_000
    assert entry["utilization"] == 1.0


def test_link_usage_skips_malformed_entries_and_capacity_failures(settings) -> None:
    """Bad usage rows are ignored and one bad capacity does not fail the sample."""
    adapter = SatGoNetemTopologyAdapter(settings)

    def fail_capacity() -> int:
        raise RuntimeError("capacity failed")

    broken_capacity = SimpleNamespace(
        source=SimpleNamespace(name="Sat2"),
        target=SimpleNamespace(name="Sat3"),
        get_capacity=fail_capacity,
    )
    topology = _usage_topology(
        links=[broken_capacity, _usage_link("Sat0", "Sat1", 2_000)],
        usage=[
            {"src": None, "dst": "Sat1", "value": 1},
            "not-a-dict",
            {"src": "Sat2", "dst": "Sat3", "value": 10},
            {"src": "Sat0", "dst": "Sat1", "value": 2_000_000},
        ],
    )

    entries = adapter.link_usage(topology)["links"]

    assert [entry["src"] for entry in entries] == ["Sat2", "Sat0"]
    assert entries[0]["capacity_kbps"] is None
    assert entries[0]["utilization"] is None
    assert entries[1]["utilization"] == 1.0


def test_link_usage_degrades_when_monitoring_fails(settings) -> None:
    """A monitor failure is logged and becomes a safe unavailable sample."""
    adapter = SatGoNetemTopologyAdapter(settings)
    topology = _usage_topology(failure=RuntimeError("monitor exploded"))

    result = adapter.link_usage(topology)

    assert result["available"] is False
    assert result["sampled_at"] is None
    assert result["links"] == []
    assert result["note"] is not None
    assert "monitor exploded" not in result["note"]
