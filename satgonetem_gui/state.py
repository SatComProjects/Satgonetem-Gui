"""Project lifecycle and per-application runtime state.

This module deliberately has no FastAPI or ``satgonetem`` imports. The concrete
topology object is opaque here; adapters own its type.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional

from .time_utils import utc_timestamp

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
    phase: str = "idle"
    progress: Optional[int] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    addressing_applied: bool = False
    _generation: int = 0
    _operation_token: int = 0
    _active_token: Optional[int] = None
    _network_operation: bool = False
    _started_monotonic: Optional[float] = field(default=None, repr=False)
    _finished_monotonic: Optional[float] = field(default=None, repr=False)
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

    @property
    def generation(self) -> int:
        """Return the installed-project generation for operation guards."""
        with self._lock:
            return self._generation

    @property
    def token(self) -> Optional[int]:
        """Return the active operation token, if any."""
        with self._lock:
            return self._active_token

    def topology_snapshot(self) -> tuple[Any, int]:
        """Return the installed topology and its generation atomically."""
        with self._lock:
            return self.topology_manager, self._generation

    def begin(
        self,
        name: str,
        save_path: str = "",
        operation: str = "create",
        precondition: Optional[Callable[[], bool]] = None,
    ) -> bool:
        """Reserve the single build slot for a new operation.

        Args:
            name: Pending project name.
            save_path: Requested save target.
            operation: ``create`` or ``load``.
            precondition: Checked under the session lock before reserving, so a
                network operation cannot start between the check and ``begin``.
        """
        with self._lock:
            if self.state is ProjectState.CREATING or self._network_operation:
                return False
            if precondition is not None and not precondition():
                return False
            self.state = ProjectState.CREATING
            self.operation = operation
            self.pending_name = name
            self.error = None
            self.phase = "validating"
            self.progress = 0
            self.started_at = utc_timestamp()
            self.finished_at = None
            self._started_monotonic = time.monotonic()
            self._finished_monotonic = None
            self._operation_token += 1
            self._active_token = self._operation_token
            return True

    def set_phase(
        self,
        phase: str,
        progress: Optional[int] = None,
        token: Optional[int] = None,
    ) -> bool:
        """Advance the phase of the active create/load operation only.

        A late phase update from a superseded or timed-out operation is
        rejected instead of overwriting the terminal state.
        """
        with self._lock:
            if self.state is not ProjectState.CREATING:
                return False
            if token is not None and token != self._active_token:
                return False
            self.phase = phase
            self.progress = progress
            return True

    def begin_network_operation(self) -> bool:
        """Reserve the network lifecycle unless a project operation is active."""
        with self._lock:
            if self.state is ProjectState.CREATING or self._network_operation:
                return False
            self._network_operation = True
            return True

    def end_network_operation(self) -> None:
        """Release the network lifecycle reservation."""
        with self._lock:
            self._network_operation = False

    @property
    def network_operation(self) -> bool:
        """Return True while a routing/container mutation is in flight."""
        with self._lock:
            return self._network_operation

    def succeed(
        self,
        topology_manager: Any,
        project_name: str,
        save_path: str = "",
        *,
        token: Optional[int] = None,
    ) -> bool:
        """Mark an operation successful and install its topology."""
        with self._lock:
            if token is not None and (
                token != self._active_token
                or self.state is not ProjectState.CREATING
            ):
                return False
            self.topology_manager = topology_manager
            self.project_name = project_name
            self.save_path = save_path
            self.state = ProjectState.LOADED
            self.phase = "ready"
            self.progress = 100
            self.finished_at = utc_timestamp()
            self._finished_monotonic = time.monotonic()
            self.pending_name = None
            self.error = None
            self.addressing_applied = False
            self._active_token = None
            self._generation += 1
            return True

    def fail(self, error: str, *, token: Optional[int] = None) -> bool:
        """Mark an operation failed while preserving any previously loaded project."""
        with self._lock:
            if token is not None and (
                token != self._active_token
                or self.state is not ProjectState.CREATING
            ):
                return False
            self.state = ProjectState.ERROR
            self.error = error or "Project operation failed."
            self.phase = "error"
            self.progress = 100
            self.finished_at = utc_timestamp()
            self._finished_monotonic = time.monotonic()
            self.pending_name = None
            self._active_token = None
            return True

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

    def context(self, name: Optional[str] = None) -> tuple[Any, str, str]:
        """Return topology, name, and save path from one atomic snapshot."""
        with self._lock:
            if self.topology_manager is None:
                return None, "", ""
            if name is not None and self.project_name != name:
                return None, "", ""
            return self.topology_manager, self.project_name or "", self.save_path

    def snapshot(self) -> Dict[str, Any]:
        """Return a JSON-serializable snapshot for the project status endpoint."""
        with self._lock:
            elapsed_ms: Optional[int] = None
            if self._started_monotonic is not None:
                finished = self._finished_monotonic
                if finished is None:
                    finished = time.monotonic()
                elapsed_ms = max(0, int((finished - self._started_monotonic) * 1000))
            return {
                "state": self.state.value,
                "operation": self.operation,
                "project_name": self.project_name,
                "pending_name": self.pending_name,
                "loaded": self.topology_manager is not None,
                "error": self.error,
                "phase": self.phase,
                "progress": self.progress,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "elapsed_ms": elapsed_ms,
            }

    def set_addressing_applied(self, applied: bool) -> None:
        """Record whether IP addressing has been applied to this project."""
        with self._lock:
            self.addressing_applied = applied

    def set_save_path(self, path: str) -> None:
        """Record the workspace file that backs the loaded project."""
        with self._lock:
            self.save_path = path

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
            self.phase = "idle"
            self.progress = None
            self.started_at = None
            self.finished_at = None
            self._started_monotonic = None
            self._finished_monotonic = None
            self.addressing_applied = False
            self._active_token = None
            self._network_operation = False
            self._generation += 1


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
        *,
        timeout_seconds: float | None = None,
        precondition: Callable[[], bool] | None = None,
        on_success: Callable[[ProjectResult], None] | None = None,
    ) -> bool:
        """Reserve the session and run the build in a background thread."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
        if not self.session.begin(
            name,
            save_path=save_path,
            operation=operation,
            precondition=precondition,
        ):
            return False
        token = self.session.token

        timer = None
        if timeout_seconds is not None:
            timer = threading.Timer(
                timeout_seconds,
                self._timeout,
                args=(token,),
            )
            timer.daemon = True

        thread = threading.Thread(
            target=self._run,
            args=(operation, runner, token, timer, on_success),
            name=f"project-{operation}",
            daemon=True,
        )
        with self._lock:
            self._thread = thread
        try:
            thread.start()
            if timer is not None:
                timer.start()
        except Exception as exc:
            if timer is not None:
                timer.cancel()
            logger.exception("Could not start the project %s thread.", operation)
            self.session.fail(_format_exception(exc), token=token)
            raise
        return True

    def _timeout(self, token: Optional[int]) -> None:
        """Fail a build that has exceeded its timeout."""
        if self.session.fail("Project build timed out.", token=token):
            logger.error("Project build timed out.")

    def _run(
        self,
        operation: str,
        runner: Callable[[], ProjectResult],
        token: Optional[int],
        timer: Optional[threading.Timer],
        on_success: Callable[[ProjectResult], None] | None = None,
    ) -> None:
        try:
            try:
                result = runner()
            except Exception as exc:
                logger.exception("Project %s failed.", operation)
                self.session.fail(_format_exception(exc), token=token)
            else:
                self.session.set_phase("finalizing", 95, token=token)
                try:
                    installed = self.session.succeed(
                        result.topology_manager,
                        result.project_name,
                        result.save_path,
                        token=token,
                    )
                except Exception as exc:
                    logger.exception(
                        "Project %s returned an invalid result.", operation
                    )
                    self.session.fail(_format_exception(exc), token=token)
                else:
                    if installed and on_success is not None:
                        try:
                            on_success(result)
                        except Exception:
                            logger.exception(
                                "Post-success cleanup failed for project %s.",
                                operation,
                            )
        except BaseException as exc:
            logger.exception("Project %s crashed unexpectedly.", operation)
            self.session.fail(_format_exception(exc), token=token)
        finally:
            if timer is not None:
                timer.cancel()

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
