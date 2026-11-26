"""Contract tests for the read-only topology reader adapter."""

from datetime import datetime
from types import SimpleNamespace

import pytest

from satgonetem_gui.adapters.topology_reader import TopologyReaderAdapter
from tests.adapter_helpers import (
    path_node,
    path_topology,
    simulation_topology,
    traffic_endpoint,
    usage_link,
    usage_topology,
)


def test_traffic_nodes_filters_and_orders_endpoints() -> None:
    """Only addressable endpoints with interfaces are returned, ground stations first."""
    adapter = TopologyReaderAdapter()
    topology = SimpleNamespace(
        ground_stations={
            10: traffic_endpoint("Gnd10", 10, city="Oslo"),
            5: traffic_endpoint("Gnd5", 5),
            8: traffic_endpoint("Gnd8", 8, city="Rome", interfaces=0),
        },
        satellites={
            12: traffic_endpoint("Sat12", 12, addressable=True),
            3: traffic_endpoint("Sat3", 3, addressable=True, interfaces=2),
            7: traffic_endpoint("Sat7", 7, addressable=False),
            9: traffic_endpoint("Sat9", 9, addressable=True, interfaces=0),
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


def test_node_detail_uses_the_core_node_type_not_the_name() -> None:
    """A ground station named with a Sat prefix is still classified as ground."""
    adapter = TopologyReaderAdapter()
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


def test_node_detail_exposes_addressability_for_satellites_only() -> None:
    """Satellite details carry the toggle state; ground stations do not."""
    adapter = TopologyReaderAdapter()
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


def test_position_sync_hook_change_is_reported() -> None:
    """A core rename of the private position hook fails loudly."""
    with pytest.raises(RuntimeError, match="_sync_node_positions"):
        TopologyReaderAdapter._sync_positions(SimpleNamespace())


def test_adapter_status_includes_simulation_transport_metadata() -> None:
    """Status exposes total steps, playback rate, and the last tick error."""
    adapter = TopologyReaderAdapter()
    topology = simulation_topology(
        update_factor=0.5,
        get_last_simulation_error=lambda: RuntimeError("tick failed"),
    )

    status = adapter.status(topology)

    assert status["total_steps"] == 120
    assert status["simulation_rate"] == 2.0
    assert status["last_simulation_error"] == "RuntimeError: tick failed"


def test_adapter_status_degrades_when_transport_metadata_is_unavailable() -> None:
    """A missing core value must not break the dashboard status read."""

    def fail() -> None:
        raise RuntimeError("core value unavailable")

    adapter = TopologyReaderAdapter()
    topology = simulation_topology(
        get_project_duration_in_timesteps=fail,
        update_factor=0,
        get_last_simulation_error=fail,
    )

    status = adapter.status(topology)

    assert status["satellites"] == 1
    assert status["total_steps"] is None
    assert status["simulation_rate"] == 1.0
    assert status["last_simulation_error"] is None


def test_adapter_status_truncates_long_simulation_errors() -> None:
    """A verbose tick error is summarized without a traceback."""
    adapter = TopologyReaderAdapter()
    topology = simulation_topology(get_last_simulation_error=lambda: RuntimeError("x" * 600))

    message = adapter.status(topology)["last_simulation_error"]

    assert message is not None
    assert message.startswith("RuntimeError: ")
    assert len(message) == 500


def test_routing_path_builds_hops_with_distance_and_delay() -> None:
    """Consecutive nodes become hops with propagation delay and running totals."""
    adapter = TopologyReaderAdapter()
    ground = path_node("Gnd10", 10)
    sat0 = path_node("Sat0", 0)
    sat1 = path_node("Sat1", 1)
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
    topology = path_topology([ground, sat0, sat1], [ground, sat0, sat1], edges, initiated=True)

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


def test_routing_path_without_a_route_returns_an_empty_result() -> None:
    """No path is a valid diagnostic answer, not an error."""
    adapter = TopologyReaderAdapter()
    sat0 = path_node("Sat0", 0)
    topology = path_topology([sat0, path_node("Sat1", 1)], [], {0: {}}, routing="dynamic-ospf")

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


def test_routing_path_rejects_identical_endpoints() -> None:
    """The same node twice cannot form a path."""
    adapter = TopologyReaderAdapter()
    sat0 = path_node("Sat0", 0)
    topology = path_topology([sat0], [sat0], {0: {}})

    with pytest.raises(ValueError, match="differ"):
        adapter.routing_path(topology, "Sat0", "Sat0")


def test_routing_path_rejects_an_unknown_node() -> None:
    """An unknown endpoint is reported before the graph is read."""
    adapter = TopologyReaderAdapter()
    topology = path_topology([path_node("Sat0", 0)], [], {0: {}})

    with pytest.raises(ValueError, match="Node not found: Missing"):
        adapter.routing_path(topology, "Sat0", "Missing")


def test_routing_path_rejects_a_path_missing_from_the_graph() -> None:
    """A path whose edge vanished is a contract error, not a silent skip."""
    adapter = TopologyReaderAdapter()
    sat0 = path_node("Sat0", 0)
    sat1 = path_node("Sat1", 1)
    topology = path_topology([sat0, sat1], [sat0, sat1], {})

    with pytest.raises(ValueError, match="no longer present"):
        adapter.routing_path(topology, "Sat0", "Sat1")


def test_links_include_delay_capacity_and_active_state() -> None:
    """The link payload carries the metrics needed by the inspector."""
    adapter = TopologyReaderAdapter()
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
                loss=1.5,
                jitter=12,
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
            "loss_percent": 1.5,
            "jitter_ms": 12,
        }
    ]


def test_link_usage_is_unavailable_when_containers_are_stopped() -> None:
    """Stopped containers are reported as an empty, unavailable sample."""
    adapter = TopologyReaderAdapter()

    result = adapter.link_usage(usage_topology(gonetem=False))

    assert result == {
        "available": False,
        "sampled_at": None,
        "links": [],
        "note": "GoNetEm containers are stopped; link usage is unavailable.",
    }
    assert "container" in result["note"].lower()


def test_link_usage_normalizes_values_capacities_and_utilization() -> None:
    """Bits per second are clamped and mapped to link capacities."""
    adapter = TopologyReaderAdapter()
    topology = usage_topology(
        links=[
            usage_link("Sat0", "Sat1", 100_000),
            usage_link("Sat1", "Gnd0", 0),
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


def test_link_usage_clamps_utilization_to_one() -> None:
    """Usage above the nominal capacity is reported as saturated."""
    adapter = TopologyReaderAdapter()
    topology = usage_topology(
        links=[usage_link("Sat0", "Sat1", 1_000)],
        usage=[{"src": "Sat0", "dst": "Sat1", "value": 5_000_000}],
    )

    entry = adapter.link_usage(topology)["links"][0]

    assert entry["value_bps"] == 5_000_000
    assert entry["capacity_kbps"] == 1_000
    assert entry["utilization"] == 1.0


def test_link_usage_skips_malformed_entries_and_capacity_failures() -> None:
    """Bad usage rows are ignored and one bad capacity does not fail the sample."""
    adapter = TopologyReaderAdapter()

    def fail_capacity() -> int:
        raise RuntimeError("capacity failed")

    broken_capacity = SimpleNamespace(
        source=SimpleNamespace(name="Sat2"),
        target=SimpleNamespace(name="Sat3"),
        get_capacity=fail_capacity,
    )
    topology = usage_topology(
        links=[broken_capacity, usage_link("Sat0", "Sat1", 2_000)],
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


def test_link_usage_degrades_when_monitoring_fails() -> None:
    """A monitor failure is logged and becomes a safe unavailable sample."""
    adapter = TopologyReaderAdapter()
    topology = usage_topology(failure=RuntimeError("monitor exploded"))

    result = adapter.link_usage(topology)

    assert result["available"] is False
    assert result["sampled_at"] is None
    assert result["links"] == []
    assert result["note"] is not None
    assert "monitor exploded" not in result["note"]
