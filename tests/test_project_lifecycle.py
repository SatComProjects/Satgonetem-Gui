"""Unit tests for the explicit project lifecycle state machine."""

import threading
import time
from types import SimpleNamespace

from satgonetem_gui.state import (
    ProjectResult,
    ProjectSession,
    ProjectState,
    ProjectTaskManager,
)


def _fake_manager() -> SimpleNamespace:
    return SimpleNamespace(status=True)


def test_begin_blocks_a_concurrent_build() -> None:
    """A second build cannot start while the first is marked as creating."""
    session = ProjectSession()

    assert session.begin("First", save_path="/tmp/first", operation="create") is True
    assert session.begin("Second", save_path="/tmp/second", operation="create") is False
    assert session.creating is True

    snapshot = session.snapshot()
    assert snapshot["state"] == ProjectState.CREATING.value
    assert snapshot["pending_name"] == "First"
    assert snapshot["loaded"] is False


def test_success_replaces_the_loaded_project() -> None:
    """A successful build clears the pending state and becomes loadable."""
    session = ProjectSession()
    manager = _fake_manager()
    session.begin("Project", save_path="/tmp/project", operation="create")

    session.succeed(manager, "Project", "/tmp/project")

    snapshot = session.snapshot()
    assert snapshot["state"] == ProjectState.LOADED.value
    assert snapshot["project_name"] == "Project"
    assert snapshot["loaded"] is True
    assert snapshot["error"] is None
    assert session.exists("Project") is True
    assert session.exists("Other") is False
    assert session.get_topology("Project") is manager


def test_failure_preserves_the_previous_project() -> None:
    """A failed replacement keeps the previously loaded project usable."""
    session = ProjectSession()
    previous = _fake_manager()
    session.succeed(previous, "Previous", "/tmp/previous")

    session.begin("Broken", save_path="", operation="create")
    session.fail("invalid constellation")

    snapshot = session.snapshot()
    assert snapshot["state"] == ProjectState.ERROR.value
    assert snapshot["error"] == "invalid constellation"
    assert snapshot["project_name"] == "Previous"
    assert snapshot["loaded"] is True
    assert session.get_topology("Previous") is previous
    assert session.get_topology("Broken") is None


def test_failure_without_previous_project_is_not_loaded() -> None:
    """The first build failing leaves the session in an explicit error state."""
    session = ProjectSession()
    session.begin("Broken", save_path="", operation="create")

    session.fail("bad shell")

    snapshot = session.snapshot()
    assert snapshot["state"] == ProjectState.ERROR.value
    assert snapshot["loaded"] is False
    assert snapshot["project_name"] is None
    assert session.exists("Broken") is False


def test_reset_returns_to_idle() -> None:
    """The test/startup reset clears loaded and pending state."""
    session = ProjectSession()
    session.succeed(_fake_manager(), "Project", "/tmp/project")
    session.begin("Next", save_path="", operation="create")

    session.reset()

    assert session.snapshot() == {
        "state": ProjectState.IDLE.value,
        "operation": None,
        "project_name": None,
        "pending_name": None,
        "loaded": False,
        "error": None,
        "phase": "idle",
        "progress": None,
        "started_at": None,
        "finished_at": None,
        "elapsed_ms": None,
    }


def test_task_manager_times_out_and_ignores_stale_success() -> None:
    """A build timeout wins over a runner that completes later."""
    session = ProjectSession()
    started = threading.Event()
    release = threading.Event()
    manager = ProjectTaskManager(session)

    def runner() -> ProjectResult:
        started.set()
        release.wait(timeout=5)
        return ProjectResult(object(), "LateProject", "")

    assert manager.start(
        "Slow",
        "",
        "create",
        runner,
        timeout_seconds=0.05,
    )
    assert started.wait(timeout=2)

    deadline = time.monotonic() + 2
    while session.state is not ProjectState.ERROR and time.monotonic() < deadline:
        time.sleep(0.01)

    assert session.state is ProjectState.ERROR
    assert "timed out" in (session.error or "")
    release.set()
    thread = manager.thread
    assert thread is not None
    thread.join(timeout=2)
    assert session.state is ProjectState.ERROR
    assert session.project_name is None


def test_task_manager_refuses_a_retry_while_the_timeout_thread_runs() -> None:
    """A retry must not overlap a build that the timeout left running."""
    session = ProjectSession()
    started = threading.Event()
    release = threading.Event()
    manager = ProjectTaskManager(session)

    def runner() -> ProjectResult:
        started.set()
        release.wait(timeout=5)
        return ProjectResult(object(), "LateProject", "")

    assert manager.start("Slow", "", "create", runner, timeout_seconds=0.05)
    assert started.wait(timeout=2)
    deadline = time.monotonic() + 2
    while session.state is not ProjectState.ERROR and time.monotonic() < deadline:
        time.sleep(0.01)

    assert session.state is ProjectState.ERROR
    assert manager.start("Retry", "", "create", runner) is False

    release.set()
    thread = manager.thread
    assert thread is not None
    thread.join(timeout=2)


def test_task_manager_marks_a_malformed_result_as_error() -> None:
    """A runner result without the expected fields cannot wedge CREATING."""
    session = ProjectSession()
    manager = ProjectTaskManager(session)

    assert manager.start("Bad", "", "create", lambda: object())
    thread = manager.thread
    assert thread is not None
    thread.join(timeout=2)

    assert session.state is ProjectState.ERROR
    assert "topology_manager" in (session.error or "")


def test_new_project_clears_addressing_state() -> None:
    """Addressing belongs to one loaded project, not the process."""
    session = ProjectSession()
    session.succeed(_fake_manager(), "First", "")
    session.set_addressing_applied(True)

    session.succeed(_fake_manager(), "Second", "")

    assert session.addressing_applied is False

    session.set_addressing_applied(True)
    session.reset()
    assert session.addressing_applied is False


def test_begin_starts_the_validating_phase() -> None:
    """A reserved build reports validating with no synthetic percentage."""
    session = ProjectSession()

    assert session.begin("Project", save_path="/tmp/project", operation="create")

    snapshot = session.snapshot()
    assert snapshot["phase"] == "validating"
    assert snapshot["progress"] == 0
    assert snapshot["started_at"] is not None
    assert snapshot["finished_at"] is None
    assert snapshot["elapsed_ms"] is not None
    assert snapshot["elapsed_ms"] >= 0


def test_phase_updates_require_the_active_creating_operation() -> None:
    """Only the current operation may advance the phase while creating."""
    session = ProjectSession()
    assert session.begin("Project", save_path="", operation="create")
    token = session.token

    assert session.set_phase("building", token=token) is True
    snapshot = session.snapshot()
    assert snapshot["phase"] == "building"
    assert snapshot["progress"] is None

    assert session.set_phase("building", 42, token=(token or 0) + 1) is False
    assert session.snapshot()["progress"] is None

    session.succeed(_fake_manager(), "Project", "")
    assert session.set_phase("building", token=token) is False
    snapshot = session.snapshot()
    assert snapshot["phase"] == "ready"
    assert snapshot["progress"] == 100
    assert snapshot["finished_at"] is not None
    assert snapshot["elapsed_ms"] is not None
    assert snapshot["elapsed_ms"] >= 0


def test_task_manager_marks_finalizing_before_installing() -> None:
    """The task manager reports finalizing just before a successful install."""
    session = ProjectSession()
    observed = {}
    original_succeed = session.succeed

    def record_phase(*args, **kwargs):
        observed["phase"] = session.snapshot()["phase"]
        observed["progress"] = session.snapshot()["progress"]
        return original_succeed(*args, **kwargs)

    session.succeed = record_phase
    manager = ProjectTaskManager(session)

    assert manager.start(
        "Phases",
        "",
        "create",
        lambda: ProjectResult(object(), "Phases", ""),
    )
    thread = manager.thread
    assert thread is not None
    thread.join(timeout=2)

    assert observed == {"phase": "finalizing", "progress": 95}
    assert session.snapshot()["phase"] == "ready"


def test_failure_records_the_error_phase() -> None:
    """A failed operation ends in the explicit error phase."""
    session = ProjectSession()
    session.begin("Broken", save_path="", operation="create")

    session.fail("bad shell")

    snapshot = session.snapshot()
    assert snapshot["phase"] == "error"
    assert snapshot["progress"] == 100
    assert snapshot["started_at"] is not None
    assert snapshot["finished_at"] is not None
    assert snapshot["elapsed_ms"] is not None
    assert snapshot["elapsed_ms"] >= 0
