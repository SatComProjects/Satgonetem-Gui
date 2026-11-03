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
