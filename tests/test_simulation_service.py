"""Unit tests for simulation transport-control orchestration."""

import asyncio
import threading

import pytest

from satgonetem_gui.errors import APIError
from satgonetem_gui.services.ports import NetworkOperationError
from satgonetem_gui.services.simulation_service import SimulationService
from satgonetem_gui.services.topology_service import TopologyService
from satgonetem_gui.state import ProjectSession
from tests.service_fakes import FakeReader, _loaded_session


class FakeSimulationController:
    """Minimal simulation controller for service tests."""

    def __init__(self, running: bool = False, failure: str | None = None) -> None:
        self.calls = []
        self.running = running
        self.failure = failure

    def simulation_running(self, topology) -> bool:
        return self.running

    def start_simulation(self, topology) -> None:
        self.calls.append("start")
        self.running = True

    def stop_simulation(self, topology) -> None:
        self.calls.append("stop")
        self.running = False

    def step_simulation(self, topology) -> None:
        self.calls.append("step")

    def reset_simulation(self, topology) -> None:
        self.calls.append("reset")

    def seek_simulation(self, topology, step: int) -> None:
        self.calls.append(("seek", step))
        if self.failure == "seek":
            raise ValueError("step out of range")

    def change_simulation_speed(self, topology, direction: str) -> None:
        self.calls.append(("speed", direction))


def _simulation_service(
    controller: FakeSimulationController | None = None,
    session: ProjectSession | None = None,
) -> tuple[SimulationService, FakeSimulationController]:
    """Return a simulation service with a fake controller."""
    session = session if session is not None else _loaded_session()
    controller = controller if controller is not None else FakeSimulationController()
    topology = TopologyService(session, FakeReader())
    return SimulationService(topology, controller), controller


@pytest.mark.parametrize("operation", ["start", "stop", "step", "reset", "seek", "speed"])
def test_simulation_operations_require_a_project(operation: str) -> None:
    """Transport controls cannot run before a project is loaded."""
    controller = FakeSimulationController()
    topology = TopologyService(ProjectSession(), FakeReader())
    service = SimulationService(topology, controller)

    async def call() -> None:
        if operation == "seek":
            await service.seek(4)
        elif operation == "speed":
            await service.change_speed("faster")
        else:
            await getattr(service, operation)()

    with pytest.raises(APIError) as error:
        asyncio.run(call())

    assert error.value.status_code == 404
    assert controller.calls == []


def test_simulation_service_forwards_each_operation() -> None:
    """Each service method calls exactly one controller operation."""
    service, controller = _simulation_service()

    async def scenario() -> None:
        await service.start()
        await service.stop()
        await service.step()
        await service.reset()
        await service.seek(7)
        await service.change_speed("faster")

    asyncio.run(scenario())

    assert controller.calls == [
        "start",
        "stop",
        "step",
        "reset",
        ("seek", 7),
        ("speed", "faster"),
    ]


@pytest.mark.parametrize("operation", ["step", "reset", "seek"])
def test_simulation_position_changes_require_a_pause(operation: str) -> None:
    """Step, reset, and seek are rejected while the loop is running."""
    controller = FakeSimulationController(running=True)
    service, _ = _simulation_service(controller)

    async def call() -> None:
        if operation == "seek":
            await service.seek(4)
        else:
            await getattr(service, operation)()

    with pytest.raises(APIError) as error:
        asyncio.run(call())

    assert error.value.status_code == 409
    assert "pause" in error.value.message.lower()
    assert controller.calls == []


def test_simulation_start_stop_and_speed_are_allowed_while_running() -> None:
    """Start, stop, and playback changes do not require a paused loop."""
    controller = FakeSimulationController(running=True)
    service, _ = _simulation_service(controller)

    async def scenario() -> None:
        await service.start()
        await service.stop()
        await service.change_speed("slower")

    asyncio.run(scenario())

    assert controller.calls == ["start", "stop", ("speed", "slower")]


def test_simulation_seek_out_of_range_maps_422() -> None:
    """A seek target the adapter rejects is a client error."""
    controller = FakeSimulationController(failure="seek")
    service, _ = _simulation_service(controller)

    with pytest.raises(APIError) as error:
        asyncio.run(service.seek(999))

    assert error.value.status_code == 422
    assert "out of range" in error.value.message


def test_simulation_stop_current_is_a_noop_without_a_project() -> None:
    """Shutdown and replacement must not touch a controller without a project."""
    controller = FakeSimulationController()
    topology = TopologyService(ProjectSession(), FakeReader())
    service = SimulationService(topology, controller)

    service.stop_current()

    assert controller.calls == []


def test_simulation_stop_current_uses_the_loaded_topology() -> None:
    """Lifecycle teardown stops the loop for the installed project."""
    service, controller = _simulation_service()

    service.stop_current()

    assert controller.calls == ["stop"]


def test_simulation_shutdown_never_raises() -> None:
    """A failing stop during shutdown is logged, not propagated."""

    class FailingSimulationController(FakeSimulationController):
        def stop_simulation(self, topology) -> None:
            raise RuntimeError("stop failed")

    service, _ = _simulation_service(FailingSimulationController())

    asyncio.run(service.shutdown())


def test_simulation_operation_gate_rejects_an_in_flight_network_operation() -> None:
    """A transport control cannot overlap routing/container work."""
    session = _loaded_session()
    service, controller = _simulation_service(session=session)
    assert session.begin_network_operation() is True
    try:
        with pytest.raises(APIError) as error:
            asyncio.run(service.start())
    finally:
        session.end_network_operation()

    assert error.value.status_code == 409
    assert "project operation" in error.value.message.lower()
    assert controller.calls == []


def test_simulation_rejects_a_project_changed_mid_operation() -> None:
    """A completed control must not report success on a replaced project."""
    session = _loaded_session()

    class ReplacingSimulationController(FakeSimulationController):
        def step_simulation(self, topology) -> None:
            super().step_simulation(topology)
            session.succeed(object(), "NewProject", "")

    service, _ = _simulation_service(ReplacingSimulationController(), session)

    with pytest.raises(APIError) as error:
        asyncio.run(service.step())

    assert error.value.status_code == 409
    assert "Project changed" in error.value.message


def test_simulation_network_failure_maps_500() -> None:
    """A controller failure is reported with a user-facing message."""

    class FailingSimulationController(FakeSimulationController):
        def start_simulation(self, topology) -> None:
            raise NetworkOperationError("loop failed to start")

    service, _ = _simulation_service(FailingSimulationController())

    with pytest.raises(APIError) as error:
        asyncio.run(service.start())

    assert error.value.status_code == 500
    assert "loop failed to start" in error.value.message


def test_simulation_timeout_keeps_the_worker_guard() -> None:
    """A timed-out control keeps its worker so a retry cannot overlap it."""
    release = threading.Event()

    class BlockingSimulationController(FakeSimulationController):
        def start_simulation(self, topology) -> None:
            release.wait(timeout=5)
            super().start_simulation(topology)

    topology = TopologyService(_loaded_session(), FakeReader())
    controller = BlockingSimulationController()
    service = SimulationService(
        topology,
        controller,
        operation_timeout_seconds=0.05,
    )

    async def scenario() -> None:
        with pytest.raises(APIError) as timeout:
            await service.start()
        assert timeout.value.status_code == 504

        with pytest.raises(APIError) as conflict:
            await service.step()
        assert conflict.value.status_code == 409

        release.set()
        await asyncio.sleep(0.1)
        await service.stop()

    asyncio.run(scenario())

    assert controller.calls == ["start", "stop"]
