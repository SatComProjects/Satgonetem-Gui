"""Unit tests for the explicit project lifecycle state machine."""

from types import SimpleNamespace

from satgonetem_gui.state import ProjectSession, ProjectState


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
    }
