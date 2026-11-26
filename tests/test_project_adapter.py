"""Contract tests for the project build/load/save adapter."""

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from satgonetem_gui.adapters.project_adapter import ProjectAdapter
from satgonetem_gui.adapters.topology_reader import TopologyReaderAdapter
from satgonetem_gui.schemas import ProjectCreateRequest
from tests.adapter_helpers import ground_data_file
from tests.factories import PROJECT_NAME, project_payload


def test_topology_adapter_round_trips_a_project(settings) -> None:
    """The adapters can build, inspect, serialize, and reload a 10x10 project."""
    adapter = ProjectAdapter(settings)
    reader = TopologyReaderAdapter()
    request = ProjectCreateRequest(**project_payload(PROJECT_NAME))

    result = adapter.build(request)
    topology = result.topology_manager

    assert result.project_name == PROJECT_NAME
    assert reader.status(topology)["satellites"] == 100
    assert len(reader.satellites(topology)) == 100
    assert len(reader.ground_stations(topology)) == 1
    assert len(reader.links(topology)) >= 200
    assert reader.node_detail(topology, "Sat0")["type"] == "satellite"
    assert reader.find_node(topology, "Sat0") is not None
    assert reader.find_node(topology, "Missing") is None

    config = adapter.config(topology, "")
    assert config["name"] == PROJECT_NAME
    assert len(config["ground_objects_properties"][0]["stations"]) == 1

    content = adapter.save(topology)
    reloaded = adapter.load(content)
    assert reloaded.project_name == PROJECT_NAME
    assert reader.status(reloaded.topology_manager)["satellites"] == 100


def test_build_writes_inline_stations_under_save_root(settings) -> None:
    """Inline station CSV files live in the managed save-root directory."""
    adapter = ProjectAdapter(settings)
    result = adapter.build(ProjectCreateRequest(**project_payload()))

    data_file = ground_data_file(result.topology_manager)

    assert data_file.parent == settings.save_root / ".satgonetem" / "ground_stations"
    assert data_file.resolve().is_relative_to(settings.save_root.resolve())
    assert data_file.is_file()


def test_build_rejects_comma_in_station_name_before_core(settings) -> None:
    """Custom station names with commas produce a clear adapter error."""
    adapter = ProjectAdapter(settings)
    payload = project_payload()
    grounds = json.loads(payload["ground_objects_properties_json"])
    grounds[0]["stations"][0]["name"] = "Berlin, DE"
    payload["ground_objects_properties_json"] = json.dumps(grounds)

    with pytest.raises(ValueError, match="must not contain commas, quotes, or newlines"):
        adapter.build(ProjectCreateRequest(**payload))


def test_build_cleans_up_station_files_when_build_fails(settings) -> None:
    """A failed build does not leave managed station files behind."""
    adapter = ProjectAdapter(settings)
    payload = project_payload(save_path="../outside.json")

    with pytest.raises(ValueError):
        adapter.build(ProjectCreateRequest(**payload))

    stable_dir = settings.save_root / ".satgonetem" / "ground_stations"
    assert list(stable_dir.glob("*.csv")) == []


def test_config_and_save_fail_loudly_when_station_file_is_missing(settings) -> None:
    """A deleted station file raises instead of silently returning no stations."""
    adapter = ProjectAdapter(settings)
    result = adapter.build(ProjectCreateRequest(**project_payload()))
    ground_data_file(result.topology_manager).unlink()

    with pytest.raises(ValueError, match="Could not read ground station file"):
        adapter.config(result.topology_manager, "")
    with pytest.raises(ValueError, match="Ground station data file is unavailable"):
        adapter.save(result.topology_manager)


def test_config_and_save_reject_external_data_files(settings, tmp_path: Path) -> None:
    """Ground files outside the packaged and save roots cannot be read or saved."""
    adapter = ProjectAdapter(settings)
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


def test_cleanup_ground_files_keeps_only_referenced_files(settings) -> None:
    """Files left by earlier builds are removed after a topology is installed."""
    adapter = ProjectAdapter(settings)
    result = adapter.build(ProjectCreateRequest(**project_payload()))
    referenced = ground_data_file(result.topology_manager)
    stale = referenced.parent / "stale-stations.csv"
    stale.write_text("0,Oslo,59.91,10.75,0.01\n", encoding="utf-8")

    adapter.cleanup_ground_files(result.topology_manager)

    assert referenced.is_file()
    assert not stale.exists()


def test_load_accepts_embedded_files_from_another_machine(settings) -> None:
    """A backup whose original data_file is outside the roots still loads."""
    adapter = ProjectAdapter(settings)
    result = adapter.build(ProjectCreateRequest(**project_payload()))
    original = ground_data_file(result.topology_manager)
    document = json.loads(adapter.save(result.topology_manager))
    original_key = str(original)
    outside_key = "/old/machine/ground_stations.csv"
    document["simulation_property"]["ground_objects_properties"][0]["data_file"] = outside_key
    document["ground_files"][outside_key] = document["ground_files"].pop(original_key)

    loaded = adapter.load(json.dumps(document))

    config = adapter.config(loaded.topology_manager, "")
    assert config["ground_objects_properties"][0]["stations"][0]["name"] == "Berlin"
    migrated = ground_data_file(loaded.topology_manager)
    assert migrated.resolve().is_relative_to(settings.save_root.resolve())
    assert migrated.is_file()


def test_load_migrates_restored_files_and_backups_remain_restorable(settings) -> None:
    """Loaded projects keep stations in the save root and round-trip backups."""
    adapter = ProjectAdapter(settings)
    result = adapter.build(ProjectCreateRequest(**project_payload()))
    original = ground_data_file(result.topology_manager)
    content = adapter.save(result.topology_manager)
    original.unlink()

    restore_dirs_before = {
        path for path in Path(tempfile.gettempdir()).glob("*_ground_files_*") if path.is_dir()
    }
    loaded = adapter.load(content)
    restore_dirs_after = {
        path for path in Path(tempfile.gettempdir()).glob("*_ground_files_*") if path.is_dir()
    }

    migrated = ground_data_file(loaded.topology_manager)
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


def test_display_name_strips_timestamp_suffixes(settings) -> None:
    """Runtime-state fallback names do not expose dependency timestamps."""
    adapter = ProjectAdapter(settings)
    topology = SimpleNamespace(
        simulation_property=None,
        project_name="Constellation_1793711838_1793711854",
    )

    assert adapter.display_name(topology) == "Constellation"


def test_adapter_writes_topology_atomically(settings, tmp_path) -> None:
    """A failed serialization leaves the previous target intact."""
    adapter = ProjectAdapter(settings)
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
