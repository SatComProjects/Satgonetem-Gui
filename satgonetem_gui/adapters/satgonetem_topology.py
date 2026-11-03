"""SatGoNetem topology adapter.

This is the only module that imports ``TopologyManager`` or its concrete
configuration models. Services depend on the protocols in ``services.ports``.
"""

import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from sat_com_builder.models import (
    GroundObjectProperty,
    SimulationProperty,
    WalkerShellProperty,
)
from satgonetem.services.topology_satcom import NetworkConfig, TopologyManager
from satgonetem.utils.satcom_fix import apply_satcom_fix

from ..config import Settings
from ..ground_stations import parse_ground_station_file, write_stations_to_temp
from ..resources import GROUND_STATIONS_DIR
from ..schemas import ProjectCreateRequest
from ..services.ports import NetworkOperationError
from ..state import ProjectResult
from ..storage import resolve_data_file, resolve_save_path

apply_satcom_fix()

logger = logging.getLogger(__name__)

DATA_SEARCH_DIR = GROUND_STATIONS_DIR


class SatGoNetemTopologyAdapter:
    """Concrete adapter around ``TopologyManager`` and its configuration models."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def build(self, payload: ProjectCreateRequest) -> ProjectResult:
        """Build a topology from a validated create request."""
        shells_raw = json.loads(payload.walker_shells_json)
        grounds_raw = json.loads(payload.ground_objects_properties_json)
        shells = [WalkerShellProperty(**shell) for shell in shells_raw]

        ground_props = []
        for ground in grounds_raw:
            ground = dict(ground)
            if ground.get("stations"):
                ground["data_file"] = str(
                    write_stations_to_temp(ground.pop("stations"))
                )
            else:
                ground.pop("stations", None)
                data_file = ground.get("data_file")
                if not data_file:
                    raise ValueError("Ground object has no stations or data_file.")
                ground["data_file"] = str(
                    resolve_data_file(data_file, DATA_SEARCH_DIR)
                )
            ground_props.append(GroundObjectProperty(**ground))

        name = payload.name.strip()
        simulation_property = SimulationProperty(
            simulation_name=name,
            start_date=payload.start_date,
            end_date=payload.end_date,
            walker_shells=shells,
            ground_objects_properties=ground_props,
        )

        topology = TopologyManager.from_satcom(simulation_property)
        topology._apply_network_config(
            NetworkConfig(
                project_name=name,
                update_time=payload.update_time,
                isl_link_capacity=payload.isl_capacity,
                gnd_link_capacity=payload.gs_capacity,
            )
        )
        topology.set_status(True)

        save_target = resolve_save_path(
            payload.save_path,
            name,
            self.settings.save_root,
        )
        if save_target is not None:
            save_target.parent.mkdir(parents=True, exist_ok=True)
            topology.to_file(str(save_target))

        return ProjectResult(
            topology_manager=topology,
            project_name=name,
            save_path=str(payload.save_path or "").strip(),
        )

    def load(self, content: str) -> ProjectResult:
        """Load a saved topology from raw JSON."""
        path = Path(tempfile.gettempdir()) / f"satgonetem_load_{os.urandom(8).hex()}.json"
        try:
            path.write_text(content, encoding="utf-8")
            topology = TopologyManager.from_file(str(path))
            topology.set_status(True)
            return ProjectResult(
                topology_manager=topology,
                project_name=self.display_name(topology),
                save_path="",
            )
        finally:
            path.unlink(missing_ok=True)

    def save(self, topology: Any) -> str:
        """Serialize a topology to JSON text."""
        path = Path(tempfile.gettempdir()) / f"satgonetem_save_{os.urandom(8).hex()}.json"
        try:
            topology.to_file(str(path))
            return path.read_text(encoding="utf-8")
        finally:
            path.unlink(missing_ok=True)

    def config(self, topology: Any, save_path: str) -> dict[str, Any]:
        """Return the editable project configuration."""
        simulation_property = getattr(topology, "simulation_property", None)
        if simulation_property is None:
            raise ValueError("Project configuration is unavailable.")

        config = simulation_property.model_dump(mode="json")
        config["name"] = simulation_property.simulation_name
        config["update_time"] = topology.update_time
        config["isl_capacity"] = topology.isl_link_capacity
        config["gs_capacity"] = topology.gnd_link_capacity
        config["save_path"] = save_path

        for ground in config.get("ground_objects_properties", []):
            data_file = ground.get("data_file")
            ground["stations"] = []
            if not data_file:
                continue
            try:
                ground["stations"] = parse_ground_station_file(Path(data_file))
            except Exception:
                logger.exception(
                    "Could not read ground station file for project config: %s",
                    data_file,
                )
        return config

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
        }

    def satellites(self, topology: Any) -> list[dict[str, Any]]:
        """Return satellite identity and positions."""
        self._sync_positions(topology)
        return [
            {
                "id": satellite.id,
                "name": satellite.name,
                "position": {
                    "latitude": satellite.position.get("latitude"),
                    "longitude": satellite.position.get("longitude"),
                    "altitude": satellite.position.get("altitude"),
                },
            }
            for satellite in topology.satellites.values()
        ]

    def ground_stations(self, topology: Any) -> list[dict[str, Any]]:
        """Return ground-station identity and positions."""
        return [
            {
                "id": station.id,
                "name": station.name,
                "city": getattr(station, "city", None),
                "position": {
                    "latitude": station.position.get("latitude"),
                    "longitude": station.position.get("longitude"),
                    "altitude": station.position.get("altitude"),
                },
            }
            for station in topology.ground_stations.values()
        ]

    def links(self, topology: Any) -> list[dict[str, Any]]:
        """Return topology links with the fields the security lab needs."""
        from ..links import link_key

        result = []
        for link in topology.links.values():
            capacity = 0
            get_capacity = getattr(link, "get_capacity", None)
            if callable(get_capacity):
                capacity = int(get_capacity() or 0)
            result.append(
                {
                    "key": link_key(link),
                    "src": link.source.name,
                    "dst": link.target.name,
                    "type": link.type,
                    "direction": link.direction,
                    "distance_km": round(link.distance / 1000.0, 2),
                    "capacity_kbps": capacity,
                    "delay_ms": int(getattr(link, "delay", 0) or 0),
                    "state": (
                        "active" if getattr(link, "is_active", True) else "inactive"
                    ),
                }
            )
        return result

    def nodes(self, topology: Any) -> list[dict[str, Any]]:
        """Return node summaries."""
        self._sync_positions(topology)
        nodes = [
            {
                "name": satellite.name,
                "type": "satellite",
                "id": satellite.id,
                "position": {
                    "latitude": satellite.position.get("latitude"),
                    "longitude": satellite.position.get("longitude"),
                    "altitude": satellite.position.get("altitude"),
                },
            }
            for satellite in topology.satellites.values()
        ]
        nodes.extend(
            {
                "name": station.name,
                "type": "ground_station",
                "id": station.id,
                "city": getattr(station, "city", None),
                "position": {
                    "latitude": station.position.get("latitude"),
                    "longitude": station.position.get("longitude"),
                    "altitude": station.position.get("altitude"),
                },
            }
            for station in topology.ground_stations.values()
        )
        return nodes

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

        data: dict[str, Any] = {
            "name": node.name,
            "type": "satellite" if name.startswith("Sat") else "ground_station",
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
        if name.startswith("Sat"):
            data["default_qos_is_on"] = getattr(node, "default_qos_is_on", False)
            data["program_specific_qos_is_on"] = getattr(
                node, "program_specific_qos_is_on", False
            )
        else:
            data["city"] = getattr(node, "city", None)
        return data

    def find_node(self, topology: Any, name: str) -> Any | None:
        """Return a concrete node object."""
        return topology.get_node_by_name(name)

    def traffic_nodes(self, topology: Any) -> list[dict[str, str]]:
        """Return addressable traffic endpoints that have at least one interface."""
        stations: list[tuple[int, dict[str, str]]] = []
        for station in topology.ground_stations.values():
            if not station.interfaces:
                continue
            city = getattr(station, "city", None)
            stations.append(
                (
                    station.id,
                    {
                        "name": station.name,
                        "type": "ground_station",
                        "label": f"{station.name} ({city})" if city else station.name,
                    },
                )
            )

        satellites: list[tuple[int, dict[str, str]]] = []
        for satellite in topology.satellites.values():
            if not satellite.is_addressable() or not satellite.interfaces:
                continue
            satellites.append(
                (
                    satellite.id,
                    {
                        "name": satellite.name,
                        "type": "satellite",
                        "label": satellite.name,
                    },
                )
            )

        stations.sort(key=lambda item: item[0])
        satellites.sort(key=lambda item: item[0])
        return [node for _, node in stations + satellites]

    def gonetem_is_on(self, topology: Any) -> bool:
        """Return whether containers are running."""
        return topology.get_gonetem_status()

    def routing_status(self, topology: Any) -> dict[str, Any]:
        """Return routing and container state without guessing addressing state."""
        return {
            "ok": True,
            "gonetem_is_on": topology.get_gonetem_status(),
            "routing_initiated": topology.get_routing_initiated(),
            "routing_method": topology.routing,
        }

    def apply_addressing(self, topology: Any) -> None:
        """Apply IP addresses and raise if the dependency reports failure."""
        result = topology.set_ip_addresses()
        if result is not None and result < 0:
            raise NetworkOperationError("IP addressing failed.")

    def init_routing(self, topology: Any, method: str) -> None:
        """Initialize routing and map the dependency's negative return code."""
        result = topology.init_routing(routing_method=method)
        if result is not None and result < 0:
            raise NetworkOperationError("Routing initialization failed.")

    def delete_routing(self, topology: Any) -> None:
        """Delete routing state; a no-op when routing was never initialized."""
        if not topology.get_routing_initiated():
            return
        result = topology.delete_routing()
        if result is not None and result < 0:
            raise NetworkOperationError("Routing deletion failed.")

    def start_gonetem(self, topology: Any) -> None:
        """Start emulated containers and verify the dependency state."""
        topology.start_gonetem()
        if not topology.get_gonetem_status():
            raise NetworkOperationError("GoNetEm failed to start.")

    def stop_gonetem(self, topology: Any) -> None:
        """Stop emulated containers without faking the loaded-project status."""
        topology.stop_gonetem()
        if topology.get_gonetem_status():
            raise NetworkOperationError("GoNetEm failed to stop.")

    @staticmethod
    def _sync_positions(topology: Any) -> None:
        """Refresh positions through the dependency's private sync hook."""
        try:
            topology._sync_node_positions()
        except Exception:
            logger.exception("Failed to sync node positions.")

    @staticmethod
    def display_name(topology: Any) -> str:
        """Return the user-facing project name without the timestamp suffix."""
        simulation_property = getattr(topology, "simulation_property", None)
        name = (
            getattr(simulation_property, "simulation_name", None)
            if simulation_property
            else None
        )
        if not name:
            raw_name = str(getattr(topology, "project_name", "") or "Loaded Project")
            name = re.sub(r"(?:_\d+)+$", "", raw_name)
        return str(name).strip() or "Loaded Project"
