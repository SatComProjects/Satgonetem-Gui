"""Project lifecycle orchestration."""

import asyncio
import json
import logging
from collections.abc import Callable
from pathlib import Path

from ..config import Settings
from ..errors import APIError
from ..ground_stations import parse_ground_station_file
from ..project_documents import validate_project_create_payload
from ..schemas import ProjectCreateRequest
from ..state import RuntimeState
from ..storage import SavePathError, resolve_save_path, safe_project_filename
from .ports import ProjectGateway

logger = logging.getLogger(__name__)

PROJECT_BUILD_TIMEOUT_SECONDS = 600.0
PROJECT_LOAD_TIMEOUT_SECONDS = 600.0


class ProjectService:
    """Coordinate project creation, loading, saving, and configuration."""

    def __init__(
        self,
        state: RuntimeState,
        gateway: ProjectGateway,
        settings: Settings,
        resources_dir: Path,
        network_running: Callable[[], bool] | None = None,
        load_timeout_seconds: float = PROJECT_LOAD_TIMEOUT_SECONDS,
    ) -> None:
        self.state = state
        self.gateway = gateway
        self.settings = settings
        self.resources_dir = resources_dir
        self.network_running = network_running
        self.load_timeout_seconds = load_timeout_seconds

    def _guard_replacement(self) -> None:
        """Refuse to replace a project while containers are still running."""
        if self.network_running is not None and self.network_running():
            raise APIError(
                409,
                "GoNetEm is running. Stop it before replacing the project.",
            )

    def _network_is_stopped(self) -> bool:
        """Return whether a replacement may start, checked under the session lock."""
        return self.network_running is None or not self.network_running()

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

        try:
            shells = json.loads(payload.walker_shells_json)
            grounds = json.loads(payload.ground_objects_properties_json)
            validate_project_create_payload(
                shells,
                grounds,
                data_search_dir=self.resources_dir,
                allowed_roots=(self.settings.save_root,),
            )
        except (json.JSONDecodeError, ValueError) as exc:
            raise APIError(
                422,
                f"Invalid project configuration: {exc}",
            ) from exc

        self._guard_replacement()

        started = self.state.project_tasks.start(
            name=name,
            save_path=str(payload.save_path or "").strip(),
            operation="create",
            runner=lambda: self.gateway.build(payload),
            timeout_seconds=PROJECT_BUILD_TIMEOUT_SECONDS,
            precondition=self._network_is_stopped,
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
        topology, project_name, save_path = self.state.project.context(name)
        if topology is None or project_name != name:
            raise APIError(404, "Project not found.")

        try:
            return self.gateway.config(topology, save_path)
        except APIError:
            raise
        except Exception as exc:
            logger.exception("Could not read project config.")
            raise APIError(500, "Could not read project config.") from exc

    async def load(self, content: str) -> str:
        """Load a project from uploaded JSON and return its display name."""
        self._guard_replacement()
        if not self.state.project.begin(
            name="",
            save_path="",
            operation="load",
            precondition=self._network_is_stopped,
        ):
            raise APIError(409, "A project operation is already running.")
        token = self.state.project.token

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self.gateway.load, content),
                timeout=self.load_timeout_seconds,
            )
        except asyncio.CancelledError:
            self.state.project.fail("Project load cancelled.", token=token)
            raise
        except asyncio.TimeoutError as exc:
            self.state.project.fail("Project load timed out.", token=token)
            raise APIError(504, "Project load timed out.") from exc
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            message = str(exc).strip() or exc.__class__.__name__
            self.state.project.fail(message, token=token)
            raise APIError(400, f"Invalid project file: {message}") from exc
        except Exception as exc:
            logger.exception("Project load failed.")
            message = str(exc).strip() or exc.__class__.__name__
            self.state.project.fail(message, token=token)
            raise APIError(500, "Project load failed.") from exc

        self.state.project.succeed(
            result.topology_manager,
            result.project_name,
            result.save_path,
            token=token,
        )
        return result.project_name

    async def save(self) -> dict:
        """Serialize the loaded project and return content plus filename."""
        topology, project_name, _save_path = self.state.project.context()
        if topology is None:
            raise APIError(404, "No project is currently loaded.")

        try:
            content = await asyncio.to_thread(self.gateway.save, topology)
        except Exception as exc:
            logger.exception("Project save failed.")
            raise APIError(500, "Project save failed.") from exc

        return {
            "content": content,
            "filename": f"{safe_project_filename(project_name or 'project')}.json",
        }
