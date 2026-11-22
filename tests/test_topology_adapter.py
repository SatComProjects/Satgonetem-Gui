"""Contract tests for the real satgonetem topology adapter."""

import json
import tempfile
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
    """v0.3.1 raises when any node failed; expose it as a network error."""
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

    with pytest.raises(ValueError, match="must not contain commas or newlines"):
        adapter.build(ProjectCreateRequest(**payload))


def test_build_cleans_up_station_files_when_build_fails(settings) -> None:
    """A failed build does not leave managed station files behind."""
    adapter = SatGoNetemTopologyAdapter(settings)
    payload = project_payload(save_path="../outside.json")

    with pytest.raises(ValueError):
        adapter.build(ProjectCreateRequest(**payload))

    stable_dir = settings.save_root / ".satgonetem" / "ground_stations"
    assert list(stable_dir.glob("*.csv")) == []


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
