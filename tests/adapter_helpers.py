"""Builders and fakes shared by the core adapter contract tests.

The project, topology reader, and network adapter tests exercise the same core
object shapes. Keeping those stand-ins here avoids duplicating harness code
across the three modules.
"""

from pathlib import Path
from types import SimpleNamespace


def traffic_endpoint(
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


def ground_data_file(topology) -> Path:
    """Return the first ground object's data file for a built topology."""
    ground = topology.simulation_property.ground_objects_properties[0]
    return Path(ground.data_file)


def simulation_topology(**overrides) -> SimpleNamespace:
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


class FakeSatellite:
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


class AddressabilityTopology:
    """Topology stand-in recording public satellite enable calls."""

    def __init__(self, satellites: list[FakeSatellite]) -> None:
        self.satellites = {satellite.id: satellite for satellite in satellites}
        self.enable_calls: list[list[FakeSatellite]] = []

    def set_addressable_satellites(self, satellites) -> None:
        targets = list(satellites)
        self.enable_calls.append(targets)
        for satellite in targets:
            satellite.set_addressable(True)


def path_node(name: str, node_id: int) -> SimpleNamespace:
    """Build a node stand-in with the identity fields the path reads."""
    return SimpleNamespace(name=name, id=node_id)


def path_topology(
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


def usage_link(src: str, dst: str, capacity_kbps: int) -> SimpleNamespace:
    """Build a link stand-in exposing only the capacity read."""
    return SimpleNamespace(
        source=SimpleNamespace(name=src),
        target=SimpleNamespace(name=dst),
        get_capacity=lambda: capacity_kbps,
    )


def usage_topology(
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


def connectivity_topology() -> SimpleNamespace:
    """Build a topology stand-in with addressable and filtered endpoints."""
    ground_stations = {
        10: traffic_endpoint("Gnd10", 10),
        5: traffic_endpoint("Gnd5", 5),
        8: traffic_endpoint("Gnd8", 8, interfaces=0),
    }
    satellites = {
        12: traffic_endpoint("Sat12", 12, addressable=True),
        3: traffic_endpoint("Sat3", 3, addressable=True, interfaces=2),
        7: traffic_endpoint("Sat7", 7, addressable=False),
        9: traffic_endpoint("Sat9", 9, addressable=True, interfaces=0),
    }
    by_name = {
        node.name: node for node in list(ground_stations.values()) + list(satellites.values())
    }
    return SimpleNamespace(
        ground_stations=ground_stations,
        satellites=satellites,
        get_node_by_name=by_name.get,
    )
