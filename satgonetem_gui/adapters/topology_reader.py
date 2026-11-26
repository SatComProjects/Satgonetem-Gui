"""Read-only topology queries for the dashboard and explorers.

Implements the ``TopologyReader``, ``LinkUsageReader``, and ``PathReader``
protocols without importing core configuration models.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from .core import PATH_NOTE, SPEED_OF_LIGHT_KM_PER_MS, addressable_endpoints, initialize_core

logger = logging.getLogger(__name__)

def _satellite_summary(satellite: Any, shells: dict[Any, str]) -> dict[str, Any]:
    """Serialize one satellite's identity and position."""
    return {
        "id": satellite.id,
        "name": satellite.name,
        "position": {
            "latitude": satellite.position.get("latitude"),
            "longitude": satellite.position.get("longitude"),
            "altitude": satellite.position.get("altitude"),
        },
        "shell": shells.get(satellite.id)
        or getattr(getattr(satellite, "shell", None), "identifier", None),
    }


def _ground_station_summary(station: Any) -> dict[str, Any]:
    """Serialize one ground station's identity and position."""
    return {
        "id": station.id,
        "name": station.name,
        "city": getattr(station, "city", None),
        "position": {
            "latitude": station.position.get("latitude"),
            "longitude": station.position.get("longitude"),
            "altitude": station.position.get("altitude"),
        },
    }


class TopologyReaderAdapter:
    """Concrete topology reader over the current ``TopologyManager``."""

    def __init__(self) -> None:
        initialize_core()

    def status(self, topology: Any) -> dict[str, Any]:
        """Return the dashboard status snapshot."""
        summary = topology.get_topology_summary()
        current_time = topology.get_current_time()
        return {
            "constellation_loaded": topology.get_status(),
            "satellites": summary.get("satellites", 0),
            "ground_stations": summary.get("ground_stations", 0),
            "links": summary.get("links", 0),
            "gonetem_is_on": topology.get_gonetem_status(),
            "simulation_updating": topology.get_running(),
            "current_step": topology.get_current_time_step(),
            "current_time": current_time.isoformat() if current_time else None,
            "total_steps": self._simulation_total_steps(topology),
            "simulation_rate": self._simulation_rate(topology),
            "last_simulation_error": self._last_simulation_error(topology),
        }


    def satellites(self, topology: Any) -> list[dict[str, Any]]:
        """Return satellite identity and positions."""
        self._sync_positions(topology)
        shells = self._shell_identifiers(topology)
        return [
            _satellite_summary(satellite, shells)
            for satellite in topology.satellites.values()
        ]



    def ground_stations(self, topology: Any) -> list[dict[str, Any]]:
        """Return ground-station identity and positions."""
        return [
            _ground_station_summary(station)
            for station in topology.ground_stations.values()
        ]


    def links(self, topology: Any) -> list[dict[str, Any]]:
        """Return topology links with current delay, capacity, and state."""
        return [
            {
                "src": link.source.name,
                "dst": link.target.name,
                "type": link.type,
                "direction": link.direction,
                "distance_km": round(link.distance / 1000.0, 2),
                "delay_ms": round(link.distance / 299_792_458 * 1000, 2),
                "capacity_kbps": int(link.get_capacity()),
                "is_active": bool(link.is_active),
                "loss_percent": float(getattr(link, "loss", 0.0) or 0.0),
                "jitter_ms": int(getattr(link, "jitter", 0) or 0),
            }
            for link in topology.links.values()
        ]

    def link_usage(self, topology: Any) -> dict[str, Any]:
        """Sample per-link bandwidth usage from the running emulation.

        Returns an unavailable sample instead of failing the dashboard when the
        containers are stopped or the core monitor raises.
        """
        if not topology.get_gonetem_status():
            return {
                "available": False,
                "sampled_at": None,
                "links": [],
                "note": ("GoNetEm containers are stopped; link usage is unavailable."),
            }

        try:
            raw_entries = topology.get_all_links_usage()
        except Exception:
            logger.exception("Could not sample link usage.")
            return {
                "available": False,
                "sampled_at": None,
                "links": [],
                "note": "Link usage could not be sampled from GoNetEm.",
            }
        if not isinstance(raw_entries, list):
            raw_entries = []

        capacities: dict[frozenset[str], int] = {}
        links = getattr(topology, "links", None)
        if isinstance(links, dict):
            for link in links.values():
                try:
                    source = link.source.name
                    target = link.target.name
                    capacity_bps = int(link.get_capacity()) * 1000
                except Exception:
                    logger.exception("Could not read a link capacity for usage sampling.")
                    continue
                if capacity_bps > 0:
                    capacities[frozenset((source, target))] = capacity_bps

        entries: list[dict[str, Any]] = []
        for raw in raw_entries:
            if not isinstance(raw, dict):
                continue
            src = raw.get("src")
            dst = raw.get("dst")
            if not isinstance(src, str) or not src:
                continue
            if not isinstance(dst, str) or not dst:
                continue
            try:
                value = int(float(raw.get("value") or 0))
            except (TypeError, ValueError, OverflowError):
                value = 0
            value_bps = max(0, value)
            capacity_bps = capacities.get(frozenset((src, dst)))
            link_type = raw.get("type")
            entries.append(
                {
                    "src": src,
                    "dst": dst,
                    "type": link_type if isinstance(link_type, str) else None,
                    "value_bps": value_bps,
                    "capacity_kbps": (capacity_bps // 1000 if capacity_bps else None),
                    "utilization": (
                        round(min(1.0, value_bps / capacity_bps), 4) if capacity_bps else None
                    ),
                }
            )

        return {
            "available": True,
            "sampled_at": datetime.now(timezone.utc).isoformat(),
            "links": entries,
            "note": None,
        }


    def nodes(self, topology: Any) -> list[dict[str, Any]]:
        """Return node summaries."""
        self._sync_positions(topology)
        shells = self._shell_identifiers(topology)
        satellites = [
            {"name": satellite.name, "type": "satellite", **_satellite_summary(satellite, shells)}
            for satellite in topology.satellites.values()
        ]
        stations = [
            {
                "name": station.name,
                "type": "ground_station",
                **_ground_station_summary(station),
            }
            for station in topology.ground_stations.values()
        ]
        return satellites + stations


    def node_detail(self, topology: Any, name: str) -> dict[str, Any] | None:
        """Return one node's detail, or None when missing."""
        node = topology.get_node_by_name(name)
        if node is None:
            return None

        self._sync_positions(topology)
        interfaces = []
        for interface in node.interfaces:
            peer_name = ""
            if interface.peer is not None:
                peer_name = getattr(interface.peer, "name", "")
            interfaces.append(
                {
                    "name": interface.name,
                    "iname": interface.get_iname(),
                    "ipv4": interface.ipv4,
                    "type": interface.type,
                    "is_active": interface.is_active,
                    "peer_name": peer_name,
                }
            )

        routing_table: list[str] = []
        try:
            routing_table = node.get_routing_table()
        except Exception:
            logger.exception("Failed to read routing table for %s", name)

        node_kind = str(getattr(node, "type", "")).lower()
        is_ground = node_kind.startswith("ground") or (not node_kind and name.startswith("Gnd"))
        data: dict[str, Any] = {
            "name": node.name,
            "type": "ground_station" if is_ground else "satellite",
            "id": node.id,
            "position": {
                "latitude": node.position.get("latitude"),
                "longitude": node.position.get("longitude"),
                "altitude": node.position.get("altitude"),
            },
            "interfaces": interfaces,
            "loopback": {"ipv4": getattr(node.loopback, "ipv4", "")},
            "routing_table": routing_table,
        }
        if is_ground:
            data["city"] = getattr(node, "city", None)
        else:
            data["default_qos_is_on"] = getattr(node, "default_qos_is_on", False)
            data["program_specific_qos_is_on"] = getattr(node, "program_specific_qos_is_on", False)
            data["addressable"] = node.is_addressable()
        return data

    def find_node(self, topology: Any, name: str) -> Any | None:
        """Return a concrete node object."""
        return topology.get_node_by_name(name)


    def traffic_nodes(self, topology: Any) -> list[dict[str, str]]:
        """Return addressable traffic endpoints that have at least one interface."""
        nodes: list[dict[str, str]] = []
        for kind, node in addressable_endpoints(topology):
            if kind == "ground_station":
                city = getattr(node, "city", None)
                label = f"{node.name} ({city})" if city else node.name
                nodes.append(
                    {"name": node.name, "type": "ground_station", "label": label}
                )
            else:
                nodes.append(
                    {"name": node.name, "type": "satellite", "label": node.name}
                )
        return nodes


    def routing_path(self, topology: Any, src: str, dst: str) -> dict[str, Any]:
        """Return a diagnostic hop-by-hop path over the current routing graph."""
        source = topology.get_node_by_name(src)
        if source is None:
            raise ValueError(f"Node not found: {src}")
        target = topology.get_node_by_name(dst)
        if target is None:
            raise ValueError(f"Node not found: {dst}")
        if source.id == target.id:
            raise ValueError("Source and destination must differ.")

        graph = topology.get_current_graph()
        path = topology.get_path_between_nodes(source, target)
        metadata: dict[str, Any] = {
            "routing_method": getattr(topology, "routing", None),
            "routing_initiated": bool(topology.get_routing_initiated()),
            "preference": getattr(topology, "preference", None),
            "path_source": "routing_graph",
            "note": PATH_NOTE,
        }
        if not path:
            return {
                "src": src,
                "dst": dst,
                "found": False,
                "hops": [],
                "node_count": 0,
                "total_distance_km": 0.0,
                "total_delay_ms": 0.0,
                **metadata,
            }

        hops: list[dict[str, Any]] = []
        total_distance_km = 0.0
        total_delay_ms = 0.0
        for current, following in zip(path, path[1:]):
            try:
                edge = graph[current.id][following.id]
            except KeyError as exc:
                raise ValueError("Path is no longer present in the current routing graph.") from exc
            distance_km = round(float(edge["distance_km"]), 2)
            delay_ms = round(float(edge["distance_km"]) / SPEED_OF_LIGHT_KM_PER_MS, 2)
            total_distance_km = round(total_distance_km + distance_km, 2)
            total_delay_ms = round(total_delay_ms + delay_ms, 2)
            hops.append(
                {
                    "source": current.name,
                    "target": following.name,
                    "type": edge.get("type"),
                    "direction": edge.get("direction"),
                    "distance_km": distance_km,
                    "delay_ms": delay_ms,
                    "cumulative_distance_km": total_distance_km,
                    "cumulative_delay_ms": total_delay_ms,
                }
            )

        return {
            "src": src,
            "dst": dst,
            "found": True,
            "hops": hops,
            "node_count": len(path),
            "total_distance_km": total_distance_km,
            "total_delay_ms": total_delay_ms,
            **metadata,
        }

    def gonetem_is_on(self, topology: Any) -> bool:
        """Return whether containers are running."""
        return topology.get_gonetem_status()

    @staticmethod
    def _simulation_total_steps(topology: Any) -> int | None:
        """Return the project duration in steps, or None when unavailable."""
        try:
            return int(topology.get_project_duration_in_timesteps())
        except Exception:
            logger.exception("Could not read the project duration in steps.")
            return None

    @staticmethod
    def _simulation_rate(topology: Any) -> float | None:
        """Return the playback multiplier, falling back to real time."""
        try:
            factor = float(getattr(topology, "update_factor", 1.0) or 1.0)
        except Exception:
            logger.exception("Could not read the simulation update factor.")
            return None
        if factor <= 0:
            return 1.0
        return round(1.0 / factor, 2)

    @staticmethod
    def _last_simulation_error(topology: Any) -> str | None:
        """Return the last loop tick error without exposing a traceback."""
        try:
            error = topology.get_last_simulation_error()
        except Exception:
            logger.exception("Could not read the last simulation error.")
            return None
        if error is None:
            return None
        return f"{type(error).__name__}: {error}"[:500]

    @staticmethod
    def _shell_identifiers(topology: Any) -> dict[Any, str]:
        """Map object ids to shell identifiers from the simulation manager."""
        manager = getattr(topology, "simulation_manager", None)
        getter = getattr(manager, "get_satellites", None)
        if not callable(getter):
            return {}
        try:
            satellites = getter()
        except Exception:
            return {}
        if isinstance(satellites, dict):
            satellites = satellites.values()
        shells = {}
        for satellite in satellites or []:
            identifier = getattr(getattr(satellite, "shell", None), "identifier", None)
            object_id = getattr(satellite, "object_id", None)
            if object_id is not None and identifier:
                shells[object_id] = str(identifier)
        return shells

    @staticmethod
    def _sync_positions(topology: Any) -> None:
        """Refresh positions through the dependency's private sync hook."""
        sync = getattr(topology, "_sync_node_positions", None)
        if not callable(sync):
            raise RuntimeError("Core contract changed: _sync_node_positions is unavailable.")
        try:
            sync()
        except Exception:
            logger.exception("Failed to sync node positions.")
