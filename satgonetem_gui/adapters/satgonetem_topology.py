"""SatGoNetem topology adapter.

This is the only module that imports ``TopologyManager`` or its concrete
configuration models. Services depend on the protocols in ``services.ports``.
"""

import json
import logging
import os
import re
import shutil
import tempfile
from datetime import timedelta
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
from ..ground_stations import (
    parse_ground_station_file,
    stable_ground_stations_dir,
    write_stations_to_temp,
)
from ..project_documents import validate_project_document
from ..resources import GROUND_STATIONS_DIR
from ..schemas import ProjectCreateRequest
from ..services.ports import NetworkOperationError
from ..state import ProjectResult
from ..storage import resolve_data_file, resolve_save_path

logger = logging.getLogger(__name__)

DATA_SEARCH_DIR = GROUND_STATIONS_DIR
_CORE_INITIALIZED = False

SPEED_OF_LIGHT_KM_PER_MS = 299.792458
PATH_NOTE = (
    "Computed over the current routing graph; this is a diagnostic path, "
    "not the live forwarding table."
)


def initialize_core() -> None:
    """Apply the pinned core's performance patch once, outside module import."""
    global _CORE_INITIALIZED
    if not _CORE_INITIALIZED:
        apply_satcom_fix()
        _CORE_INITIALIZED = True


class SatGoNetemTopologyAdapter:
    """Concrete adapter around ``TopologyManager`` and its configuration models."""

    def __init__(self, settings: Settings) -> None:
        initialize_core()
        self.settings = settings

    def build(self, payload: ProjectCreateRequest) -> ProjectResult:
        """Build a topology from a validated create request."""
        shells_raw = json.loads(payload.walker_shells_json)
        grounds_raw = json.loads(payload.ground_objects_properties_json)
        shells = [WalkerShellProperty(**shell) for shell in shells_raw]

        created_ground_files: list[Path] = []
        try:
            ground_props = []
            for ground in grounds_raw:
                ground = dict(ground)
                if ground.get("stations"):
                    path = write_stations_to_temp(
                        ground.pop("stations"),
                        directory=stable_ground_stations_dir(self.settings.save_root),
                    )
                    created_ground_files.append(path)
                    ground["data_file"] = str(path)
                else:
                    ground.pop("stations", None)
                    data_file = ground.get("data_file")
                    if not data_file:
                        raise ValueError(
                            "Ground object has no stations or data_file."
                        )
                    ground["data_file"] = str(
                        resolve_data_file(
                            data_file,
                            DATA_SEARCH_DIR,
                            allowed_roots=(self.settings.save_root,),
                        )
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
                self._write_topology_atomically(topology, save_target)

            return ProjectResult(
                topology_manager=topology,
                project_name=name,
                save_path=str(payload.save_path or "").strip(),
            )
        except Exception:
            for path in created_ground_files:
                path.unlink(missing_ok=True)
            raise

    def load(self, content: str) -> ProjectResult:
        """Load a saved topology from raw JSON.

        The uploaded document is validated before the core can write any
        embedded ground file. Core-restored files are then copied into the
        managed save-root directory so backups and later saves stay portable.
        """
        validate_project_document(
            content,
            (DATA_SEARCH_DIR, self.settings.save_root),
        )

        path = Path(tempfile.gettempdir()) / f"satgonetem_load_{os.urandom(8).hex()}.json"
        restore_prefix = f"{path.stem}_ground_files_"
        try:
            path.write_text(content, encoding="utf-8")
            topology = TopologyManager.from_file(str(path))
            self._migrate_restored_ground_files(topology, restore_prefix)
            topology.set_status(True)
            return ProjectResult(
                topology_manager=topology,
                project_name=self.display_name(topology),
                save_path="",
            )
        finally:
            path.unlink(missing_ok=True)
            self._remove_restore_dirs(restore_prefix)

    def cleanup_ground_files(self, topology: Any) -> None:
        """Delete managed station files no longer referenced by the topology."""
        simulation_property = getattr(topology, "simulation_property", None)
        keep: set[Path] = set()
        if simulation_property is not None:
            for ground in simulation_property.ground_objects_properties:
                data_file = getattr(ground, "data_file", None)
                if not data_file:
                    continue
                try:
                    keep.add(Path(data_file).resolve())
                except (OSError, RuntimeError):
                    continue

        stable_dir = stable_ground_stations_dir(self.settings.save_root)
        if not stable_dir.is_dir():
            return
        for candidate in stable_dir.iterdir():
            if not candidate.is_file():
                continue
            try:
                if candidate.resolve() in keep:
                    continue
            except (OSError, RuntimeError):
                continue
            candidate.unlink(missing_ok=True)

    def save(self, topology: Any) -> str:
        """Serialize a topology to JSON text."""
        self._require_ground_files(topology)
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
                resolved = resolve_data_file(
                    data_file,
                    DATA_SEARCH_DIR,
                    allowed_roots=(self.settings.save_root,),
                )
                ground["stations"] = parse_ground_station_file(resolved)
            except (OSError, ValueError) as exc:
                raise ValueError(
                    "Could not read ground station file: "
                    f"{data_file!r}"
                ) from exc
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
            "total_steps": self._simulation_total_steps(topology),
            "simulation_rate": self._simulation_rate(topology),
            "last_simulation_error": self._last_simulation_error(topology),
        }

    def simulation_running(self, topology: Any) -> bool:
        """Return whether the core simulation loop is running."""
        return bool(topology.get_running())

    def start_simulation(self, topology: Any) -> None:
        """Start the core simulation loop."""
        topology.start()

    def stop_simulation(self, topology: Any) -> None:
        """Stop the core simulation loop and join its thread."""
        topology.stop()

    def step_simulation(self, topology: Any) -> None:
        """Advance the simulation by one step."""
        topology.next_step()

    def reset_simulation(self, topology: Any) -> None:
        """Reset the simulation clock to the project start."""
        topology.reset_simulation()

    def seek_simulation(self, topology: Any, step: int) -> None:
        """Jump to an absolute step and rebuild routing through the core."""
        total_steps = topology.get_project_duration_in_timesteps()
        if step < 0 or step > total_steps:
            raise ValueError(f"Step {step} is outside 0..{total_steps}.")
        target = topology.start_time + timedelta(
            seconds=step * topology.update_time
        )
        topology.move_to_time(target)

    def change_simulation_speed(self, topology: Any, direction: str) -> None:
        """Change playback speed through the core's public controls."""
        if direction == "faster":
            topology.speed_up()
        elif direction == "slower":
            topology.speed_down()
        else:
            raise ValueError(f"Unknown simulation speed direction: {direction!r}")

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
        """Return topology links."""
        return [
            {
                "src": link.source.name,
                "dst": link.target.name,
                "type": link.type,
                "direction": link.direction,
                "distance_km": round(link.distance / 1000.0, 2),
            }
            for link in topology.links.values()
        ]

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

        node_kind = str(getattr(node, "type", "")).lower()
        is_ground = node_kind.startswith("ground") or (
            not node_kind and name.startswith("Gnd")
        )
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
            data["program_specific_qos_is_on"] = getattr(
                node, "program_specific_qos_is_on", False
            )
            data["addressable"] = node.is_addressable()
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

    def satellite_addressability(self, topology: Any) -> dict[str, Any]:
        """Return the addressable satellite names and the satellite total."""
        satellites = list(topology.satellites.values())
        return {
            "addressable": sorted(
                satellite.name
                for satellite in satellites
                if satellite.is_addressable()
            ),
            "total": len(satellites),
        }

    def set_satellites_addressable(
        self,
        topology: Any,
        enabled: bool,
        names: list[str] | None = None,
    ) -> int:
        """Enable or disable addressability for all or selected satellites."""
        satellites = list(topology.satellites.values())
        if names is None:
            targets = satellites
        else:
            by_name = {satellite.name: satellite for satellite in satellites}
            missing = [name for name in names if name not in by_name]
            if missing:
                raise ValueError(f"Unknown satellite: {missing[0]}")
            targets = [by_name[name] for name in names]

        if not targets:
            return 0
        if enabled:
            topology.set_addressable_satellites(targets)
        else:
            for satellite in targets:
                satellite.set_addressable(False)
        return len(targets)

    def routing_status(self, topology: Any) -> dict[str, Any]:
        """Return routing and container state without guessing addressing state."""
        return {
            "ok": True,
            "gonetem_is_on": topology.get_gonetem_status(),
            "routing_initiated": topology.get_routing_initiated(),
            "routing_method": topology.routing,
        }

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

    def apply_addressing(self, topology: Any) -> None:
        """Apply IP addresses and raise if the dependency reports failure."""
        try:
            result = topology.set_ip_addresses()
        except RuntimeError as exc:
            raise NetworkOperationError(str(exc)) from exc
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
        """Start emulated containers and clean up a partial startup on failure."""
        try:
            topology.start_gonetem()
            if not topology.get_gonetem_status():
                raise NetworkOperationError("GoNetEm failed to start.")
        except Exception:
            try:
                topology.stop_gonetem()
            except Exception:
                logger.exception("Failed to clean up a partial GoNetEm startup.")
            raise

    def stop_gonetem(self, topology: Any) -> None:
        """Stop emulated containers without faking the loaded-project status."""
        topology.stop_gonetem()
        if topology.get_gonetem_status():
            raise NetworkOperationError("GoNetEm failed to stop.")

    @staticmethod
    def _write_topology_atomically(topology: Any, target: Path) -> None:
        """Write through a sibling temp file and atomically replace the target."""
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
        )
        os.close(descriptor)
        temp_path = Path(temp_name)
        try:
            topology.to_file(str(temp_path))
            temp_path.replace(target)
        finally:
            temp_path.unlink(missing_ok=True)

    def _require_ground_files(self, topology: Any) -> None:
        """Fail before core serialization when a referenced data file is unusable.

        The core silently omits data files it cannot read, which produces a
        backup that cannot be restored. Preflight every path instead.
        """
        simulation_property = getattr(topology, "simulation_property", None)
        if simulation_property is None:
            return
        for ground in simulation_property.ground_objects_properties:
            data_file = getattr(ground, "data_file", None)
            if not data_file:
                continue
            try:
                resolved = resolve_data_file(
                    data_file,
                    DATA_SEARCH_DIR,
                    allowed_roots=(self.settings.save_root,),
                )
            except (OSError, ValueError) as exc:
                raise ValueError(
                    "Ground station data file is unavailable: "
                    f"{data_file!r}"
                ) from exc
            if resolved != Path(data_file):
                ground.data_file = str(resolved)

    def _migrate_restored_ground_files(
        self,
        topology: Any,
        restore_prefix: str,
    ) -> None:
        """Move core-restored files into the managed save-root directory."""
        restore_dirs = [
            candidate
            for candidate in Path(tempfile.gettempdir()).glob(f"{restore_prefix}*")
            if candidate.is_dir()
        ]
        if not restore_dirs:
            return

        simulation_property = getattr(topology, "simulation_property", None)
        if simulation_property is None:
            return

        stable_dir = stable_ground_stations_dir(self.settings.save_root)
        stable_dir.mkdir(parents=True, exist_ok=True)
        copied: list[Path] = []
        try:
            for ground in simulation_property.ground_objects_properties:
                data_file = getattr(ground, "data_file", None)
                if not data_file:
                    continue
                source = Path(data_file)
                if not any(
                    source.resolve().is_relative_to(directory.resolve())
                    for directory in restore_dirs
                ):
                    continue
                if not source.is_file():
                    raise ValueError(
                        "Restored ground station file is missing: "
                        f"{data_file!r}"
                    )
                descriptor, name = tempfile.mkstemp(
                    dir=stable_dir,
                    prefix=f"{source.stem}-",
                    suffix=source.suffix or ".csv",
                )
                os.close(descriptor)
                target = Path(name)
                copied.append(target)
                shutil.copyfile(source, target)
                ground.data_file = str(target)
        except Exception:
            for target in copied:
                target.unlink(missing_ok=True)
            raise

    @staticmethod
    def _remove_restore_dirs(restore_prefix: str) -> None:
        """Remove the core's temporary ground-file restore directories."""
        for directory in Path(tempfile.gettempdir()).glob(f"{restore_prefix}*"):
            if directory.is_dir():
                shutil.rmtree(directory, ignore_errors=True)

    @staticmethod
    def _sync_positions(topology: Any) -> None:
        """Refresh positions through the dependency's private sync hook."""
        sync = getattr(topology, "_sync_node_positions", None)
        if not callable(sync):
            raise RuntimeError(
                "Core contract changed: _sync_node_positions is unavailable."
            )
        try:
            sync()
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
