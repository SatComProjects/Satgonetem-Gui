"""Pure tests for topology health checks and serializers."""

import json
import xml.etree.ElementTree as ET

import pytest

from satgonetem_gui.topology_export import serialize_topology
from satgonetem_gui.topology_health import build_health


def _node(
    name: str,
    *,
    node_type: str = "satellite",
    latitude: float | None = 0.0,
    longitude: float | None = 0.0,
    altitude: float | None = 550.0,
    city: str | None = None,
) -> dict:
    return {
        "name": name,
        "type": node_type,
        "id": 1,
        "city": city,
        "position": {
            "latitude": latitude,
            "longitude": longitude,
            "altitude": altitude,
        },
    }


def _link(
    src: str,
    dst: str,
    *,
    link_type: str = "InterSatelliteLink",
    capacity_kbps: int = 100_000,
    delay_ms: float = 1.0,
) -> dict:
    return {
        "src": src,
        "dst": dst,
        "type": link_type,
        "direction": "undefined",
        "distance_km": 300.0,
        "delay_ms": delay_ms,
        "capacity_kbps": capacity_kbps,
        "is_active": True,
    }


def _check(health: dict, check_id: str) -> dict:
    return next(check for check in health["checks"] if check["id"] == check_id)


def test_health_reports_isolated_and_incomplete_nodes() -> None:
    """Isolated nodes are informational; missing positions are warnings."""
    nodes = [
        _node("Sat0"),
        _node("Sat1", latitude=1.0),
        _node("Gnd0", node_type="ground_station", altitude=0.0),
        _node("Gnd1", node_type="ground_station", latitude=None, longitude=None),
    ]
    links = [_link("Sat0", "Sat1"), _link("Sat0", "Gnd0")]

    health = build_health(nodes, links)

    assert health["nodes"] == 4
    assert health["links"] == 2
    assert health["healthy"] is False
    isolated = _check(health, "isolated_nodes")
    assert isolated["count"] == 1
    assert isolated["severity"] == "info"
    assert isolated["items"] == ["Gnd1"]
    missing = _check(health, "missing_positions")
    assert missing["count"] == 1
    assert missing["severity"] == "warning"


def test_health_reports_duplicate_positions() -> None:
    """Rounded duplicate coordinates are grouped into one finding."""
    nodes = [
        _node("Sat0", latitude=10.0, longitude=20.0, altitude=550.0),
        _node("Sat1", latitude=10.0, longitude=20.0, altitude=550.0),
        _node("Sat2", latitude=11.0, longitude=20.0, altitude=550.0),
    ]
    links = [_link("Sat0", "Sat1"), _link("Sat1", "Sat2")]

    health = build_health(nodes, links)

    duplicates = _check(health, "duplicate_positions")
    assert duplicates["count"] == 1
    assert duplicates["items"] == ["Sat0/Sat1"]
    assert health["healthy"] is False


def test_health_reports_link_problems() -> None:
    """Zero capacity, negative delay, self-links, and duplicate pairs warn."""
    nodes = [_node("Sat0"), _node("Sat1"), _node("Sat2")]
    links = [
        _link("Sat0", "Sat1", capacity_kbps=0),
        _link("Sat0", "Sat1"),
        _link("Sat1", "Sat2", delay_ms=-1.0),
        _link("Sat2", "Sat2"),
    ]

    health = build_health(nodes, links)

    assert _check(health, "zero_capacity_links")["count"] == 1
    assert _check(health, "negative_delay_links")["count"] == 1
    assert _check(health, "self_links")["count"] == 1
    assert _check(health, "duplicate_links")["count"] == 1
    assert health["healthy"] is False


def test_health_is_clean_for_a_connected_graph() -> None:
    """A connected, complete topology reports healthy with zero findings."""
    nodes = [_node("Sat0"), _node("Sat1", latitude=1.0)]
    links = [_link("Sat0", "Sat1")]

    health = build_health(nodes, links)

    assert health["healthy"] is True
    assert all(check["count"] == 0 for check in health["checks"])
    assert all(check["items"] == [] for check in health["checks"])


def test_health_caps_items_but_keeps_the_count() -> None:
    """Item previews are bounded while the total count stays accurate."""
    nodes = [_node(f"Sat{index}", latitude=float(index)) for index in range(25)]

    health = build_health(nodes, [])

    isolated = _check(health, "isolated_nodes")
    assert isolated["count"] == 25
    assert len(isolated["items"]) == 20
    assert health["healthy"] is True


def test_health_accepts_an_empty_topology() -> None:
    """Empty inputs are valid and healthy."""
    health = build_health([], [])

    assert health["nodes"] == 0
    assert health["links"] == 0
    assert health["healthy"] is True
    assert {check["id"] for check in health["checks"]} == {
        "isolated_nodes",
        "missing_positions",
        "duplicate_positions",
        "zero_capacity_links",
        "negative_delay_links",
        "self_links",
        "duplicate_links",
    }


def test_json_export_contains_the_graph() -> None:
    """JSON exports are parseable and preserve nodes and links."""
    nodes = [_node("Sat0"), _node("Gnd0", node_type="ground_station", altitude=0.0)]
    links = [_link("Sat0", "Gnd0")]

    filename, content, content_type = serialize_topology("json", nodes, links)

    assert filename == "topology.json"
    assert content_type == "application/json"
    payload = json.loads(content)
    assert payload["schema"] == "satgonetem-gui.topology/1"
    assert payload["nodes"] == nodes
    assert payload["links"] == links


def test_dot_export_quotes_and_escapes_names() -> None:
    """DOT identifiers and attributes survive quotes and backslashes."""
    nodes = [_node('Sat "0"'), _node("Gnd\\1", node_type="ground_station", altitude=0.0)]
    links = [_link('Sat "0"', "Gnd\\1")]

    filename, content, content_type = serialize_topology("dot", nodes, links)

    assert filename == "topology.dot"
    assert content_type == "text/vnd.graphviz"
    assert content.startswith("graph topology {")
    assert '"Sat \\"0\\""' in content
    assert '"Gnd\\\\1"' in content
    assert '"Sat \\"0\\"" -- "Gnd\\\\1"' in content


def test_graphml_export_escapes_xml_entities() -> None:
    """GraphML is well-formed even when names contain XML metacharacters."""
    nodes = [_node("Sat<0>&"), _node("Gnd0", node_type="ground_station", altitude=0.0)]
    links = [_link("Sat<0>&", "Gnd0")]

    filename, content, content_type = serialize_topology("graphml", nodes, links)

    assert filename == "topology.graphml"
    assert content_type == "application/graphml+xml"
    root = ET.fromstring(content)
    assert root.tag.endswith("graphml")
    node_ids = [element.attrib["id"] for element in root.iter() if element.tag.endswith("node")]
    assert "Sat<0>&" in node_ids


def test_unknown_export_format_is_rejected() -> None:
    """The pure serializer refuses unsupported formats."""
    with pytest.raises(ValueError):
        serialize_topology("pdf", [], [])
