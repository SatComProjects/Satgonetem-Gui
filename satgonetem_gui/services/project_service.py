"""Project lifecycle orchestration."""

import asyncio
import json
import logging
from pathlib import Path

from ..config import Settings
from ..errors import APIError
from ..ground_stations import parse_ground_station_file
from ..schemas import ProjectCreateRequest
from ..state import RuntimeState
from ..storage import SavePathError, resolve_save_path
from .ports import ProjectGateway

logger = logging.getLogger(__name__)


class ProjectService:
    """Coordinate project creation, loading, saving, and configuration."""

    def __init__(
        self,
        state: RuntimeState,
        gateway: ProjectGateway,
        settings: Settings,
        resources_dir: Path,
    ) -> None:
        self.state = state
        self.gateway = gateway
        self.settings = settings
        self.resources_dir = resources_dir

    def presets(self) -> list[dict]:
        """Return the bundled ground-station presets."""
        return [
            {"name": path.stem, "stations": parse_ground_station_file(path)}
            for path in sorted(self.resources_dir.glob("*.txt"))
        ]

    def start_create(self, payload: ProjectCreateRequest) -> None:
        """Validate and dispatch a background project build."""
        name = payload.name.strip()
        if not name:
            raise APIError(400, "Project name is required.")

        try:
            resolve_save_path(payload.save_path, name, self.settings.save_root)
        except SavePathError as exc:
            raise APIError(400, str(exc)) from exc

        started = self.state.project_tasks.start(
            name=name,
            save_path=str(payload.save_path or "").strip(),
            operation="create",
            runner=lambda: self.gateway.build(payload),
        )
        if not started:
            raise APIError(409, "A project operation is already running.")

    def status(self) -> dict:
        """Return the current project lifecycle snapshot."""
        return self.state.project.snapshot()

    def exists(self, name: str) -> bool:
        """Return whether the named project is loaded."""
        return self.state.project.exists(name)

    def config(self, name: str) -> dict:
        """Return the editable configuration for a loaded project."""
        topology = self.state.project.get_topology(name)
        if topology is None:
            raise APIError(404, "Project not found.")

        try:
            return self.gateway.config(topology, self.state.project.save_path)
        except APIError:
            raise
        except Exception as exc:
            logger.exception("Could not read project config.")
            raise APIError(500, "Could not read project config.") from exc

    async def load(self, content: str) -> str:
        """Load a project from uploaded JSON and return its display name."""
        if not self.state.project.begin(name="", save_path="", operation="load"):
            raise APIError(409, "A project operation is already running.")

        try:
            result = await asyncio.to_thread(self.gateway.load, content)
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            message = str(exc).strip() or exc.__class__.__name__
            self.state.project.fail(message)
            raise APIError(400, f"Invalid project file: {message}") from exc
        except Exception as exc:
            logger.exception("Project load failed.")
            message = str(exc).strip() or exc.__class__.__name__
            self.state.project.fail(message)
            raise APIError(500, "Project load failed.") from exc

        self.state.project.succeed(
            result.topology_manager,
            result.project_name,
            result.save_path,
        )
        return result.project_name

    async def save(self) -> dict:
        """Serialize the loaded project and return content plus filename."""
        topology = self.state.project.get_topology()
        if topology is None:
            raise APIError(404, "No project is currently loaded.")

        try:
            content = await asyncio.to_thread(self.gateway.save, topology)
        except Exception as exc:
            logger.exception("Project save failed.")
            raise APIError(500, "Project save failed.") from exc

        name = (self.state.project.project_name or "project").replace(" ", "_")
        return {"content": content, "filename": f"{name}.json"}
