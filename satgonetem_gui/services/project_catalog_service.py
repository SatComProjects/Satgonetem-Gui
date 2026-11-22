"""Project workspace/catalog orchestration."""

import asyncio
import csv
import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import Settings
from ..errors import APIError
from ..ground_stations import STATION_FIELDS, parse_ground_station_file
from ..state import RuntimeState
from ..storage import (
    SavePathError,
    iter_workspace_project_files,
    resolve_data_file,
    resolve_workspace_project,
    validate_workspace_target,
    workspace_filename,
    workspace_project_id,
    workspace_relative,
    write_workspace_project,
)
from .ports import ProjectGateway
from .project_service import ProjectService

logger = logging.getLogger(__name__)


def _count(value: Any) -> int | None:
    """Return a non-negative integer from saved JSON, or None when malformed."""
    if isinstance(value, bool):
        return None
    try:
        count = int(value)
    except (TypeError, ValueError):
        return None
    return count if count >= 0 else None


def _count_station_rows(content: str) -> int:
    """Count parseable rows in embedded ground-station CSV content."""
    count = 0
    for row in csv.reader(io.StringIO(content)):
        if not row or all(not field.strip() for field in row):
            continue
        if len(row) != len(STATION_FIELDS):
            continue
        try:
            int(row[0])
            float(row[2])
            float(row[3])
            float(row[4])
        except ValueError:
            continue
        count += 1
    return count


class ProjectCatalogService:
    """List, load, duplicate, delete, and save workspace project files.

    Client-supplied values are treated as opaque ids or names. Every path is
    resolved by ``storage`` and must remain inside the configured save root;
    responses never expose an absolute filesystem path.
    """

    def __init__(
        self,
        state: RuntimeState,
        project: ProjectService,
        gateway: ProjectGateway,
        settings: Settings,
    ) -> None:
        self.state = state
        self.project = project
        self.gateway = gateway
        self.settings = settings

    def list_projects(self) -> dict:
        """Return the workspace catalog, skipping unreadable project files."""
        projects: list[dict] = []
        warnings: list[str] = []
        for path in iter_workspace_project_files(self.settings.save_root):
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                logger.exception("Could not read workspace project file.")
                warnings.append(f"Skipped unreadable project file: {path.name}")
                continue
            try:
                document = json.loads(content)
            except (json.JSONDecodeError, ValueError):
                warnings.append(f"Skipped malformed project file: {path.name}")
                continue
            if not isinstance(document, dict):
                warnings.append(f"Skipped malformed project file: {path.name}")
                continue
            try:
                projects.append(self._summary(path, document))
            except (OSError, TypeError, ValueError):
                logger.exception("Could not summarize workspace project file.")
                warnings.append(f"Skipped unreadable project file: {path.name}")
        return {"ok": True, "projects": projects, "warnings": warnings}

    async def load_project(self, project_id: str) -> str:
        """Load a workspace project by opaque id and return its display name."""
        path = resolve_workspace_project(self.settings.save_root, project_id)
        if path is None:
            raise APIError(404, "Project not found.")
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise APIError(404, "Project not found.") from exc
        except (OSError, UnicodeDecodeError) as exc:
            logger.exception("Could not read workspace project.")
            raise APIError(500, "Could not read the workspace project.") from exc
        return await self.project.load(content, save_path=str(path))

    def duplicate_project(self, project_id: str, name: str) -> dict:
        """Copy a workspace project file under a new name without loading it."""
        source = resolve_workspace_project(self.settings.save_root, project_id)
        if source is None:
            raise APIError(404, "Project not found.")
        clean_name, target = self._workspace_target(name)
        if target.exists():
            raise APIError(409, "A project with that name already exists.")
        try:
            content = source.read_text(encoding="utf-8")
            write_workspace_project(target, content)
        except (OSError, UnicodeDecodeError) as exc:
            logger.exception("Could not duplicate workspace project.")
            raise APIError(500, "Could not duplicate the workspace project.") from exc
        return self._saved_response(target, clean_name, overwritten=False)

    def delete_project(self, project_id: str) -> None:
        """Delete a workspace project file, refusing the current save target."""
        path = resolve_workspace_project(self.settings.save_root, project_id)
        if path is None:
            raise APIError(404, "Project not found.")
        if self._is_current_save_path(path):
            raise APIError(
                409,
                "The project loaded from the workspace cannot be deleted.",
            )
        try:
            path.unlink()
        except FileNotFoundError as exc:
            raise APIError(404, "Project not found.") from exc
        except OSError as exc:
            logger.exception("Could not delete workspace project.")
            raise APIError(500, "Could not delete the workspace project.") from exc

    async def save_current_to(self, name: str, overwrite: bool = False) -> dict:
        """Serialize the loaded project into the workspace under ``name``."""
        clean_name, target = self._workspace_target(name)
        topology, _project_name, _save_path = self.state.project.context()
        if topology is None:
            raise APIError(404, "No project is currently loaded.")
        existed = target.exists()
        if existed and not overwrite:
            raise APIError(409, "A project with that name already exists.")

        content = await self._serialize(topology)
        self._write(target, content)
        self.state.project.set_save_path(str(target))
        return self._saved_response(target, clean_name, overwritten=existed)

    async def save_current_in_place(self) -> dict:
        """Atomically overwrite the loaded project's workspace file."""
        topology, project_name, save_path = self.state.project.context()
        if topology is None:
            raise APIError(404, "No project is currently loaded.")
        if not save_path.strip():
            raise APIError(
                409,
                "This project is not saved in the workspace yet. Save it to the workspace first.",
            )
        target = self._session_target(save_path)

        content = await self._serialize(topology)
        self._write(target, content)
        self.state.project.set_save_path(str(target))
        return self._saved_response(
            target,
            project_name or target.stem,
            overwritten=True,
        )

    def _summary(self, path: Path, document: dict) -> dict:
        """Build one catalog entry without exposing the absolute path."""
        stat = path.stat()
        simulation = document.get("simulation_property")
        satellites: int | None = None
        ground_stations: int | None = None
        shells: int | None = None
        valid = True

        if simulation is None:
            name = path.stem
        elif not isinstance(simulation, dict):
            name = path.stem
            valid = False
        else:
            raw_name = simulation.get("simulation_name")
            name = raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() else path.stem
            satellites, shells, valid = self._shell_counts(simulation)
            ground_stations, grounds_valid = self._ground_counts(document, simulation)
            valid = valid and grounds_valid

        return {
            "id": workspace_project_id(workspace_relative(path, self.settings.save_root)),
            "name": name,
            "filename": path.name,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            "size_bytes": stat.st_size,
            "satellites": satellites,
            "ground_stations": ground_stations,
            "shells": shells,
            "valid": valid,
        }

    @staticmethod
    def _shell_counts(simulation: dict) -> tuple[int | None, int | None, bool]:
        """Return satellite total, shell count, and structural validity."""
        walker_shells = simulation.get("walker_shells")
        if walker_shells is None:
            return 0, 0, True
        if not isinstance(walker_shells, list):
            return None, None, False

        satellites = 0
        valid = True
        for shell in walker_shells:
            constellation = shell.get("constellation_property") if isinstance(shell, dict) else None
            if not isinstance(constellation, dict):
                valid = False
                continue
            planes = _count(constellation.get("amount_of_orbit_plane"))
            per_plane = _count(constellation.get("amount_of_satellite_per_orbit_plane"))
            if planes is None or per_plane is None:
                valid = False
                continue
            satellites += planes * per_plane
        return satellites, len(walker_shells), valid

    def _ground_counts(
        self,
        document: dict,
        simulation: dict,
    ) -> tuple[int | None, bool]:
        """Return the station total and structural validity.

        Inline station lists are counted directly. Saved projects usually
        reference a ``data_file`` instead, so the embedded ``ground_files``
        content is counted, falling back to a contained file read. When neither
        is available the count is zero and the project stays valid.
        """
        grounds = simulation.get("ground_objects_properties")
        if grounds is None:
            return 0, True
        if not isinstance(grounds, list):
            return None, False

        stations = 0
        valid = True
        for ground in grounds:
            if not isinstance(ground, dict):
                valid = False
                continue
            inline = ground.get("stations")
            if isinstance(inline, list):
                stations += len(inline)
                continue
            if inline is not None:
                valid = False
                continue
            stations += self._data_file_count(document, ground.get("data_file"))
        return stations, valid

    def _data_file_count(self, document: dict, data_file: Any) -> int:
        """Best-effort station count for a data-file-only ground object."""
        if not isinstance(data_file, str) or not data_file.strip():
            return 0
        ground_files = document.get("ground_files")
        if isinstance(ground_files, dict):
            embedded = ground_files.get(data_file)
            if isinstance(embedded, dict):
                content = embedded.get("content")
                if isinstance(content, str):
                    return _count_station_rows(content)
        try:
            resolved = resolve_data_file(
                data_file,
                self.settings.save_root,
                allowed_roots=(self.settings.save_root,),
            )
            return len(parse_ground_station_file(resolved))
        except (OSError, ValueError):
            return 0

    def _workspace_target(self, name: str) -> tuple[str, Path]:
        """Return a stripped name and its contained workspace file target."""
        clean_name = name.strip()
        if not clean_name:
            raise APIError(422, "Project name is required.")
        try:
            target = validate_workspace_target(
                self.settings.save_root / workspace_filename(clean_name),
                self.settings.save_root,
            )
        except SavePathError as exc:
            raise APIError(
                422,
                "Project name cannot be saved in the workspace.",
            ) from exc
        return clean_name, target

    def _session_target(self, save_path: str) -> Path:
        """Resolve the loaded project's save path inside the workspace."""
        candidate = Path(save_path).expanduser()
        if not candidate.is_absolute():
            candidate = self.settings.save_root / candidate
        try:
            return validate_workspace_target(candidate, self.settings.save_root)
        except SavePathError as exc:
            raise APIError(
                409,
                "This project is not saved in the workspace. Use Save to workspace first.",
            ) from exc

    def _is_current_save_path(self, path: Path) -> bool:
        """Return whether ``path`` is the loaded project's save target."""
        _topology, _project_name, save_path = self.state.project.context()
        if not save_path.strip():
            return False
        candidate = Path(save_path).expanduser()
        if not candidate.is_absolute():
            candidate = self.settings.save_root / candidate
        try:
            return candidate.resolve() == path
        except (OSError, RuntimeError, ValueError):
            return False

    async def _serialize(self, topology: Any) -> str:
        """Serialize the loaded topology off the event loop."""
        try:
            content = await asyncio.to_thread(self.gateway.save, topology)
        except Exception as exc:
            logger.exception("Project save failed.")
            raise APIError(500, "Project save failed.") from exc
        if not isinstance(content, str):
            logger.error("Project save returned non-text content.")
            raise APIError(500, "Project save failed.")
        return content

    @staticmethod
    def _write(target: Path, content: str) -> None:
        """Write one contained workspace file atomically."""
        try:
            write_workspace_project(target, content)
        except OSError as exc:
            logger.exception("Could not write workspace project.")
            raise APIError(500, "Could not write the workspace project.") from exc

    def _saved_response(
        self,
        target: Path,
        name: str,
        *,
        overwritten: bool,
    ) -> dict:
        """Build the shared workspace-save response without absolute paths."""
        return {
            "ok": True,
            "id": workspace_project_id(workspace_relative(target, self.settings.save_root)),
            "name": name,
            "filename": target.name,
            "overwritten": overwritten,
        }
