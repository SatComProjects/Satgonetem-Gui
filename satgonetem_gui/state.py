"""Project lifecycle and per-application runtime state.

This module deliberately has no FastAPI or ``satgonetem`` imports. The concrete
topology object is opaque here; adapters own its type.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class ProjectState(str, Enum):
    """Lifecycle state of the active project session."""

    IDLE = "idle"
    CREATING = "creating"
    LOADED = "loaded"
    ERROR = "error"


@dataclass(frozen=True)
class ProjectResult:
    """Result returned by a successful project build or load."""

    topology_manager: Any
    project_name: str
    save_path: str = ""


@dataclass
class ProjectSession:
    """Loaded project plus the state of the latest build/load operation.

    The loaded topology is preserved while a replacement is being built and if
    that replacement fails. The explicit state lets the UI stop polling and
    show the failure instead of waiting for a project that will never arrive.
    """

    topology_manager: Any = None
    project_name: Optional[str] = None
    save_path: str = ""
    state: ProjectState = ProjectState.IDLE
    operation: Optional[str] = None
    pending_name: Optional[str] = None
    error: Optional[str] = None
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    @property
    def creating(self) -> bool:
        """Return True while a create/load operation is in progress."""
        with self._lock:
            return self.state is ProjectState.CREATING

    @property
    def loaded(self) -> bool:
        """Return True when a topology is currently available."""
        with self._lock:
            return self.topology_manager is not None

    def begin(
        self,
        name: str,
        save_path: str = "",
        operation: str = "create",
    ) -> bool:
        """Reserve the single build slot for a new operation."""
        with self._lock:
            if self.state is ProjectState.CREATING:
                return False
            self.state = ProjectState.CREATING
            self.operation = operation
            self.pending_name = name
            self.error = None
            return True

    def succeed(
        self,
        topology_manager: Any,
        project_name: str,
        save_path: str = "",
    ) -> None:
        """Mark an operation successful and install its topology."""
        with self._lock:
            self.topology_manager = topology_manager
            self.project_name = project_name
            self.save_path = save_path
            self.state = ProjectState.LOADED
            self.pending_name = None
            self.error = None

    def fail(self, error: str) -> None:
        """Mark an operation failed while preserving any previously loaded project."""
        with self._lock:
            self.state = ProjectState.ERROR
            self.error = error or "Project operation failed."
            self.pending_name = None

    def exists(self, name: str) -> bool:
        """Return True when the named project is loaded and no build is running."""
        with self._lock:
            return (
                self.state is not ProjectState.CREATING
                and self.topology_manager is not None
                and self.project_name == name
            )

    def get_topology(self, name: Optional[str] = None) -> Any:
        """Return the loaded topology, optionally checked against a project name."""
        with self._lock:
            if self.topology_manager is None:
                return None
            if name is not None and self.project_name != name:
                return None
            return self.topology_manager

    def snapshot(self) -> Dict[str, Any]:
        """Return a JSON-serializable snapshot for the project status endpoint."""
        with self._lock:
            return {
                "state": self.state.value,
                "operation": self.operation,
                "project_name": self.project_name,
                "pending_name": self.pending_name,
                "loaded": self.topology_manager is not None,
                "error": self.error,
            }

    def reset(self) -> None:
        """Clear all project state. Intended for tests and startup."""
        with self._lock:
            self.topology_manager = None
            self.project_name = None
            self.save_path = ""
            self.state = ProjectState.IDLE
            self.operation = None
            self.pending_name = None
            self.error = None


def _format_exception(exc: BaseException) -> str:
    """Return a non-empty, user-facing message for an exception."""
    message = str(exc).strip()
    return message or exc.__class__.__name__


class ProjectTaskManager:
    """Run one project build at a time and record its outcome on the session."""

    def __init__(self, session: ProjectSession) -> None:
        self.session = session
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(
        self,
        name: str,
        save_path: str,
        operation: str,
        runner: Callable[[], ProjectResult],
    ) -> bool:
        """Reserve the session and run the build in a background thread."""
        if not self.session.begin(name, save_path=save_path, operation=operation):
            return False

        thread = threading.Thread(
            target=self._run,
            args=(operation, runner),
            name=f"project-{operation}",
            daemon=True,
        )
        with self._lock:
            self._thread = thread
        try:
            thread.start()
        except Exception as exc:
            logger.exception("Could not start the project %s thread.", operation)
            self.session.fail(_format_exception(exc))
            raise
        return True

    def _run(self, operation: str, runner: Callable[[], ProjectResult]) -> None:
        try:
            result = runner()
        except Exception as exc:
            logger.exception("Project %s failed.", operation)
            self.session.fail(_format_exception(exc))
        else:
            self.session.succeed(
                result.topology_manager,
                result.project_name,
                result.save_path,
            )

    @property
    def thread(self) -> Optional[threading.Thread]:
        """Return the most recently started build thread, if any."""
        with self._lock:
            return self._thread


@dataclass
class RuntimeState:
    """Per-application runtime state; no module-level singleton."""

    project: ProjectSession = field(default_factory=ProjectSession)
    project_tasks: ProjectTaskManager = field(init=False)

    def __post_init__(self) -> None:
        self.project_tasks = ProjectTaskManager(self.project)
