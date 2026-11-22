"""Pure serializers for topology graph exports."""

import json
from typing import Any, Iterable

GRAPH_SCHEMA = "satgonetem-gui.topology/1"
GRAPHML_NAMESPACE = "http://graphml.graphdrawing.org/xmlns"

_NODE_KEYS = (
    ("node_type", "type", "string"),
    ("node_city", "city", "string"),
    ("node_latitude", "latitude", "double"),
    ("node_longitude", "longitude", "double"),
    ("node_altitude", "altitude", "double"),
)
_EDGE_KEYS = (
    ("edge_type", "type", "string"),
    ("edge_direction", "direction", "string"),
    ("edge_capacity_kbps", "capacity_kbps", "int"),
    ("edge_delay_ms", "delay_ms", "double"),
    ("edge_active", "active", "boolean"),
)


def _records(items: Any) -> list[dict[str, Any]]:
    """Return only well-formed mapping entries from a payload list."""
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _position(node: dict[str, Any]) -> dict[str, Any]:
    """Return a node's position mapping, or an empty mapping."""
    position = node.get("position")
    return position if isinstance(position, dict) else {}


def _text(value: Any) -> str:
    """Return a printable value, using an empty string for None."""
    return "" if value is None else str(value)


def _bool_text(value: Any) -> str:
    """Return a lowercase Graphviz/GraphML boolean."""
    return "true" if bool(value) else "false"


def _dot_escape(value: str) -> str:
    """Escape backslashes, quotes, and line breaks inside a DOT string."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "\\r").replace("\n", "\\n")


def _dot_value(value: Any) -> str:
    """Render one DOT attribute value as an escaped quoted string."""
    if isinstance(value, bool):
        return _bool_text(value)
    return _dot_escape(_text(value))


def _dot_attributes(attributes: Iterable[tuple[str, Any]]) -> str:
    """Render an attribute list as ``[key="value", ...]``."""
    return "[" + ", ".join(f'{key}="{_dot_value(value)}"' for key, value in attributes) + "]"


def _serialize_json(nodes: list[dict], links: list[dict]) -> tuple[str, str, str]:
    """Serialize the graph as the tagged JSON download envelope."""
    payload = {"schema": GRAPH_SCHEMA, "nodes": nodes, "links": links}
    content = json.dumps(payload, indent=2) + "\n"
    return "topology.json", content, "application/json"


def _serialize_dot(nodes: list[dict], links: list[dict]) -> tuple[str, str, str]:
    """Serialize the graph as a Graphviz DOT undirected graph."""
    lines = ["graph topology {"]
    for node in _records(nodes):
        position = _position(node)
        attributes: list[tuple[str, Any]] = [("type", node.get("type"))]
        if node.get("city") is not None:
            attributes.append(("city", node.get("city")))
        attributes.extend(
            (
                ("latitude", position.get("latitude")),
                ("longitude", position.get("longitude")),
                ("altitude", position.get("altitude")),
            )
        )
        name = _dot_escape(_text(node.get("name")))
        lines.append(f'  "{name}" {_dot_attributes(attributes)};')

    for link in _records(links):
        attributes = (
            ("type", link.get("type")),
            ("direction", link.get("direction")),
            ("capacity_kbps", link.get("capacity_kbps")),
            ("delay_ms", link.get("delay_ms")),
            ("active", link.get("is_active")),
        )
        src = _dot_escape(_text(link.get("src")))
        dst = _dot_escape(_text(link.get("dst")))
        lines.append(f'  "{src}" -- "{dst}" {_dot_attributes(attributes)};')

    lines.append("}")
    return "topology.dot", "\n".join(lines) + "\n", "text/vnd.graphviz"


def _xml_escape(value: Any) -> str:
    """Escape XML text and attribute content."""
    return (
        _text(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _serialize_graphml(nodes: list[dict], links: list[dict]) -> tuple[str, str, str]:
    """Serialize the graph as GraphML with typed node and edge keys."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<graphml xmlns="{GRAPHML_NAMESPACE}">',
    ]
    for key_id, name, key_type in _NODE_KEYS:
        lines.append(f'  <key id="{key_id}" for="node" attr.name="{name}" attr.type="{key_type}"/>')
    for key_id, name, key_type in _EDGE_KEYS:
        lines.append(f'  <key id="{key_id}" for="edge" attr.name="{name}" attr.type="{key_type}"/>')
    lines.append('  <graph id="topology" edgedefault="undirected">')

    for node in _records(nodes):
        position = _position(node)
        lines.append(f'    <node id="{_xml_escape(node.get("name"))}">')
        node_values = (
            ("node_type", node.get("type")),
            ("node_city", node.get("city")),
            ("node_latitude", position.get("latitude")),
            ("node_longitude", position.get("longitude")),
            ("node_altitude", position.get("altitude")),
        )
        for key_id, value in node_values:
            lines.append(f'      <data key="{key_id}">{_xml_escape(value)}</data>')
        lines.append("    </node>")

    for link in _records(links):
        lines.append(
            f'    <edge source="{_xml_escape(link.get("src"))}" '
            f'target="{_xml_escape(link.get("dst"))}">'
        )
        edge_values = (
            ("edge_type", link.get("type")),
            ("edge_direction", link.get("direction")),
            ("edge_capacity_kbps", link.get("capacity_kbps")),
            ("edge_delay_ms", link.get("delay_ms")),
            ("edge_active", _bool_text(link.get("is_active"))),
        )
        for key_id, value in edge_values:
            lines.append(f'      <data key="{key_id}">{_xml_escape(value)}</data>')
        lines.append("    </edge>")

    lines.extend(("  </graph>", "</graphml>"))
    return "topology.graphml", "\n".join(lines) + "\n", "application/graphml+xml"


def serialize_topology(fmt: str, nodes: list[dict], links: list[dict]) -> tuple[str, str, str]:
    """Serialize one topology snapshot as ``(filename, content, content_type)``."""
    serializers = {
        "json": _serialize_json,
        "dot": _serialize_dot,
        "graphml": _serialize_graphml,
    }
    serializer = serializers.get(fmt)
    if serializer is None:
        raise ValueError(f"Unsupported topology export format: {fmt}")
    return serializer(nodes, links)
