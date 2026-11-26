"""Unit tests for project create, load, and save lifecycle orchestration."""

import asyncio
import threading
import time

import pytest

from satgonetem_gui.config import Settings
from satgonetem_gui.errors import APIError
from satgonetem_gui.schemas import ProjectCreateRequest
from satgonetem_gui.services.project_service import ProjectService
from satgonetem_gui.state import ProjectResult, ProjectState, RuntimeState
from tests.factories import project_payload


def test_project_replacement_is_blocked_while_network_runs(tmp_path) -> None:
    """Replacing a project while containers run would orphan the old network."""
    service = ProjectService(
        RuntimeState(),
        object(),
        Settings("127.0.0.1", 8000, tmp_path),
        tmp_path,
        network_running=lambda: True,
    )

    with pytest.raises(APIError) as create_error:
        service.start_create(ProjectCreateRequest(**project_payload("Replacement")))
    with pytest.raises(APIError) as load_error:
        asyncio.run(service.load("{}"))

    assert create_error.value.status_code == 409
    assert load_error.value.status_code == 409
    assert "Stop it before replacing" in create_error.value.message


def test_project_load_timeout_marks_the_session_failed(tmp_path) -> None:
    """A slow load releases the single-flight slot with an error."""

    class SlowGateway:
        def load(self, _content):
            time.sleep(0.2)
            return None

    service = ProjectService(
        RuntimeState(),
        SlowGateway(),
        Settings("127.0.0.1", 8000, tmp_path),
        tmp_path,
        load_timeout_seconds=0.05,
    )

    with pytest.raises(APIError) as error:
        asyncio.run(service.load("{}"))

    assert error.value.status_code == 504
    assert service.state.project.state is ProjectState.ERROR
    assert "timed out" in (service.state.project.error or "")
    assert service.state.project.token is None


def test_project_load_retry_is_blocked_while_the_worker_runs(tmp_path) -> None:
    """A timed-out load worker keeps a guard so a retry cannot overlap it."""

    class SlowGateway:
        def load(self, _content):
            time.sleep(0.2)
            return None

    service = ProjectService(
        RuntimeState(),
        SlowGateway(),
        Settings("127.0.0.1", 8000, tmp_path),
        tmp_path,
        load_timeout_seconds=0.05,
    )

    async def scenario() -> None:
        with pytest.raises(APIError) as error:
            await service.load("{}")
        assert error.value.status_code == 504

        with pytest.raises(APIError) as conflict:
            await service.load("{}")
        assert conflict.value.status_code == 409

    asyncio.run(scenario())


def test_project_load_is_blocked_while_a_build_thread_runs(tmp_path) -> None:
    """A load cannot start while a timed-out build is still running."""
    state = RuntimeState()
    started = threading.Event()
    release = threading.Event()
    service = ProjectService(
        state,
        object(),
        Settings("127.0.0.1", 8000, tmp_path),
        tmp_path,
    )

    def runner():
        started.set()
        release.wait(timeout=5)
        return ProjectResult(object(), "LateProject", "")

    assert state.project_tasks.start("Slow", "", "create", runner, timeout_seconds=5)
    assert started.wait(timeout=2)

    with pytest.raises(APIError) as error:
        asyncio.run(service.load("{}"))

    assert error.value.status_code == 409
    release.set()
    thread = state.project_tasks.thread
    assert thread is not None
    thread.join(timeout=2)


def test_project_create_is_blocked_while_a_load_worker_runs(tmp_path) -> None:
    """A create cannot start while a timed-out load worker is still running."""

    class SlowGateway:
        def load(self, _content):
            time.sleep(0.2)
            return None

    service = ProjectService(
        RuntimeState(),
        SlowGateway(),
        Settings("127.0.0.1", 8000, tmp_path),
        tmp_path,
        load_timeout_seconds=0.05,
    )

    async def scenario() -> None:
        with pytest.raises(APIError) as timeout:
            await service.load("{}")
        assert timeout.value.status_code == 504

        with pytest.raises(APIError) as conflict:
            service.start_create(ProjectCreateRequest(**project_payload("New")))
        assert conflict.value.status_code == 409

    asyncio.run(scenario())


def test_project_load_cancellation_marks_the_session_failed(tmp_path) -> None:
    """Cancelling the request releases the creating state."""
    started = threading.Event()
    release = threading.Event()

    class BlockingGateway:
        def load(self, _content):
            started.set()
            release.wait(timeout=5)
            return None

    service = ProjectService(
        RuntimeState(),
        BlockingGateway(),
        Settings("127.0.0.1", 8000, tmp_path),
        tmp_path,
    )

    async def scenario() -> None:
        task = asyncio.create_task(service.load("{}"))
        await asyncio.to_thread(started.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        release.set()

    asyncio.run(scenario())

    assert service.state.project.state is ProjectState.ERROR
    assert "cancelled" in (service.state.project.error or "")
    assert service.state.project.token is None


def test_project_save_uses_one_topology_snapshot(tmp_path) -> None:
    """A concurrent project swap must not change the saved content/filename pair."""
    runtime = RuntimeState()
    runtime.project.succeed(object(), "ProjectA", "")
    started = threading.Event()
    release = threading.Event()

    class Gateway:
        def save(self, _topology):
            started.set()
            release.wait(timeout=5)
            return "CONTENT_A"

    service = ProjectService(
        runtime,
        Gateway(),
        Settings("127.0.0.1", 8000, tmp_path),
        tmp_path,
    )

    async def scenario() -> dict:
        task = asyncio.create_task(service.save())
        await asyncio.to_thread(started.wait, 2)
        runtime.project.succeed(object(), "ProjectB", "")
        release.set()
        return await task

    assert asyncio.run(scenario()) == {
        "content": "CONTENT_A",
        "filename": "ProjectA.json",
    }


def test_project_replacement_is_blocked_while_a_network_operation_is_active(
    tmp_path,
) -> None:
    """A build cannot start while a routing/container mutation is in flight."""
    state = RuntimeState()
    assert state.project.begin_network_operation() is True
    service = ProjectService(
        state,
        object(),
        Settings("127.0.0.1", 8000, tmp_path),
        tmp_path,
    )

    with pytest.raises(APIError) as error:
        service.start_create(ProjectCreateRequest(**project_payload("Replacement")))

    assert error.value.status_code == 409
    state.project.end_network_operation()


def test_project_create_stops_the_simulation_loop_before_building(tmp_path) -> None:
    """Replacing a project must not leave the old loop running."""
    calls = []

    class Gateway:
        def build(self, payload):
            calls.append("build")
            return ProjectResult(object(), payload.name, "")

        def cleanup_ground_files(self, _topology):
            pass

    state = RuntimeState()
    service = ProjectService(
        state,
        Gateway(),
        Settings("127.0.0.1", 8000, tmp_path),
        tmp_path,
        stop_simulation=lambda: calls.append("stop_simulation"),
    )

    service.start_create(ProjectCreateRequest(**project_payload("First")))
    state.project_tasks.thread.join(timeout=5)

    assert calls == ["build"]


def test_project_create_stops_a_running_loop_before_building(tmp_path) -> None:
    """A loaded project's loop is stopped before its replacement is built."""
    calls = []
    state = RuntimeState()
    state.project.succeed(object(), "Existing", "")

    class Gateway:
        def build(self, payload):
            calls.append("build")
            return ProjectResult(object(), payload.name, "")

        def cleanup_ground_files(self, _topology):
            pass

    service = ProjectService(
        state,
        Gateway(),
        Settings("127.0.0.1", 8000, tmp_path),
        tmp_path,
        stop_simulation=lambda: calls.append("stop_simulation"),
    )

    service.start_create(ProjectCreateRequest(**project_payload("Replacement")))
    state.project_tasks.thread.join(timeout=5)

    assert calls == ["stop_simulation", "build"]


def test_project_load_stops_the_simulation_loop_before_loading(tmp_path) -> None:
    """A load stops the old loop before the replacement topology is read."""
    calls = []
    state = RuntimeState()
    state.project.succeed(object(), "Existing", "")

    class Gateway:
        def load(self, _content):
            calls.append("load")
            return ProjectResult(object(), "Loaded", "")

    service = ProjectService(
        state,
        Gateway(),
        Settings("127.0.0.1", 8000, tmp_path),
        tmp_path,
        stop_simulation=lambda: calls.append("stop_simulation"),
    )

    assert asyncio.run(service.load("{}")) == "Loaded"
    assert calls == ["stop_simulation", "load"]


def test_project_load_skips_stopping_when_nothing_is_loaded(tmp_path) -> None:
    """A first load has no simulation loop to stop."""
    calls = []

    class Gateway:
        def load(self, _content):
            calls.append("load")
            return ProjectResult(object(), "Loaded", "")

    service = ProjectService(
        RuntimeState(),
        Gateway(),
        Settings("127.0.0.1", 8000, tmp_path),
        tmp_path,
        stop_simulation=lambda: calls.append("stop_simulation"),
    )

    assert asyncio.run(service.load("{}")) == "Loaded"
    assert calls == ["load"]


def test_project_create_fails_when_the_simulation_cannot_stop(tmp_path) -> None:
    """A failed stop fails the project operation instead of being swallowed."""
    state = RuntimeState()
    state.project.succeed(object(), "Existing", "")

    class Gateway:
        def build(self, payload):
            return ProjectResult(object(), payload.name, "")

    def fail_stop() -> None:
        raise RuntimeError("simulation stop failed")

    service = ProjectService(
        state,
        Gateway(),
        Settings("127.0.0.1", 8000, tmp_path),
        tmp_path,
        stop_simulation=fail_stop,
    )

    service.start_create(ProjectCreateRequest(**project_payload("Replacement")))
    state.project_tasks.thread.join(timeout=5)

    assert state.project.state is ProjectState.ERROR
    assert "simulation stop failed" in (state.project.error or "")


def test_project_create_reports_the_building_phase(tmp_path) -> None:
    """The background runner advances from validating to building to ready."""
    runtime = RuntimeState()
    observed = {}

    class Gateway:
        def build(self, payload):
            observed["phase"] = runtime.project.snapshot()["phase"]
            return ProjectResult(object(), payload.name, "")

    service = ProjectService(
        runtime,
        Gateway(),
        Settings("127.0.0.1", 8000, tmp_path),
        tmp_path,
    )

    service.start_create(ProjectCreateRequest(**project_payload("Phases")))
    thread = runtime.project_tasks.thread
    assert thread is not None
    thread.join(timeout=5)

    assert observed["phase"] == "building"
    snapshot = runtime.project.snapshot()
    assert snapshot["phase"] == "ready"
    assert snapshot["progress"] == 100
    assert snapshot["started_at"] is not None
    assert snapshot["finished_at"] is not None


def test_project_load_reports_the_loading_phase(tmp_path) -> None:
    """A load advances from validating to loading to ready."""
    runtime = RuntimeState()
    observed = {}

    class Gateway:
        def load(self, _content):
            observed["phase"] = runtime.project.snapshot()["phase"]
            return ProjectResult(object(), "Loaded", "")

        def cleanup_ground_files(self, _topology):
            pass

    service = ProjectService(
        runtime,
        Gateway(),
        Settings("127.0.0.1", 8000, tmp_path),
        tmp_path,
    )

    assert asyncio.run(service.load("{}")) == "Loaded"
    assert observed["phase"] == "loading"
    snapshot = runtime.project.snapshot()
    assert snapshot["phase"] == "ready"
    assert snapshot["progress"] == 100
    assert snapshot["finished_at"] is not None
