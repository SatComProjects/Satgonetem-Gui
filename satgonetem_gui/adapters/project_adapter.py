"""Project build, load, save, and ground-file lifecycle adapter.

The only adapter module that constructs core project configuration models and
performs project persistence. Services depend on the ``ProjectGateway`` protocol.
"""

import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from sat_com_builder.models import (
    GroundObjectProperty,
    SimulationProperty,
    WalkerShellProperty,
)
from satgonetem.services.topology_satcom import NetworkConfig, TopologyManager

from ..config import Settings
from ..ground_stations import (
    parse_ground_station_file,
    stable_ground_stations_dir,
    write_stations_to_temp,
)
from ..project_documents import validate_project_document
from ..schemas import ProjectCreateRequest
from ..state import ProjectResult
from ..storage import resolve_data_file, resolve_save_path
from .core import DATA_SEARCH_DIR, display_name, initialize_core

logger = logging.getLogger(__name__)


class ProjectAdapter:
    """Concrete ``ProjectGateway`` around ``TopologyManager``."""

    def __init__(self, settings: Settings) -> None:
        initialize_core()
        self.settings = settings

    @staticmethod
    def display_name(topology: Any) -> str:
        """Return the user-facing project name without the timestamp suffix."""
        return display_name(topology)

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
                        raise ValueError("Ground object has no stations or data_file.")
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
                raise ValueError(f"Could not read ground station file: {data_file!r}") from exc
        return config

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
                raise ValueError(f"Ground station data file is unavailable: {data_file!r}") from exc
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
                    raise ValueError(f"Restored ground station file is missing: {data_file!r}")
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