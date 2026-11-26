"""Unit tests for routing, path lookup, and container lifecycle orchestration."""

import asyncio
import threading

import pytest

from satgonetem_gui.errors import APIError
from satgonetem_gui.services.ports import NetworkOperationError
from satgonetem_gui.services.routing_service import RoutingService
from satgonetem_gui.services.topology_service import TopologyService
from satgonetem_gui.state import ProjectSession
from tests.service_fakes import FakeReader, _loaded_session, _ready_topology


class FakeController:
    """Minimal routing controller for service tests."""

    def __init__(self, fail_init: bool = False) -> None:
        self.calls = []
        self.fail_init = fail_init

    def routing_status(self, topology):
        return {
            "ok": True,
            "gonetem_is_on": True,
            "routing_initiated": "init_routing" in self.calls,
            "routing_method": "static",
        }

    def apply_addressing(self, topology):
        self.calls.append("apply_addressing")

    def init_routing(self, topology, method):
        self.calls.append("init_routing")
        if self.fail_init:
            raise NetworkOperationError("routing failed")

    def delete_routing(self, topology):
        self.calls.append("delete_routing")

    def start_gonetem(self, topology):
        self.calls.append("start_gonetem")

    def stop_gonetem(self, topology):
        self.calls.append("stop_gonetem")


class FakePathReader:
    """Minimal routing-path reader for service tests."""

    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls = []

    def routing_path(self, topology, src, dst):
        self.calls.append((src, dst))
        if self.error is not None:
            raise self.error
        if self.response is not None:
            return self.response
        return {
            "src": src,
            "dst": dst,
            "found": False,
            "hops": [],
            "node_count": 0,
            "total_distance_km": 0.0,
            "total_delay_ms": 0.0,
            "routing_method": "static",
            "routing_initiated": False,
            "preference": None,
            "path_source": "routing_graph",
            "note": "Computed over the current routing graph.",
        }


def _path_payload(src: str = "Sat0", dst: str = "Sat1") -> dict:
    """Return a complete routing-path response for pass-through tests."""
    return {
        "src": src,
        "dst": dst,
        "found": True,
        "hops": [
            {
                "source": src,
                "target": dst,
                "type": "InterSatelliteLink",
                "direction": "UP",
                "distance_km": 1000.0,
                "delay_ms": 3.34,
                "cumulative_distance_km": 1000.0,
                "cumulative_delay_ms": 3.34,
            }
        ],
        "node_count": 2,
        "total_distance_km": 1000.0,
        "total_delay_ms": 3.34,
        "routing_method": "static",
        "routing_initiated": True,
        "preference": "latency_no_preference",
        "path_source": "routing_graph",
        "note": (
            "Computed over the current routing graph; this is a diagnostic "
            "path, not the live forwarding table."
        ),
    }


def test_routing_apply_requires_gonetem() -> None:
    """Routing is rejected while the containers are stopped."""
    session = _loaded_session()
    topology = TopologyService(session, FakeReader(gonetem=False))
    service = RoutingService(topology, FakeController())

    with pytest.raises(APIError) as error:
        asyncio.run(service.apply("static"))

    assert error.value.status_code == 409


def test_routing_path_returns_the_reader_response() -> None:
    """The diagnostic path is returned from the path reader unchanged."""
    topology = TopologyService(_loaded_session(), FakeReader())
    reader = FakePathReader(_path_payload())
    service = RoutingService(topology, FakeController(), reader=reader)

    result = service.path("Sat0", "Sat1")

    assert result == _path_payload()
    assert reader.calls == [("Sat0", "Sat1")]


def test_routing_path_without_a_route_is_not_found_but_not_an_error() -> None:
    """Disconnected endpoints return found=False instead of raising."""
    topology = TopologyService(_loaded_session(), FakeReader())
    reader = FakePathReader()
    service = RoutingService(topology, FakeController(), reader=reader)

    result = service.path("Sat0", "Sat1")

    assert result["found"] is False
    assert result["hops"] == []
    assert result["node_count"] == 0


def test_routing_path_rejects_the_same_endpoint() -> None:
    """A path needs two different endpoints."""
    topology = TopologyService(_loaded_session(), FakeReader())
    service = RoutingService(topology, FakeController(), reader=FakePathReader())

    with pytest.raises(APIError) as error:
        service.path("Sat0", "Sat0")

    assert error.value.status_code == 422
    assert "different" in error.value.message.lower()


@pytest.mark.parametrize(
    ("src", "dst"),
    [("Gnd", "Sat0"), ("Sat0", "Gndabc"), ("", "Sat0")],
)
def test_routing_path_rejects_malformed_names(src: str, dst: str) -> None:
    """Names outside the Sat/Gnd grammar are 404s before the reader runs."""
    topology = TopologyService(_loaded_session(), FakeReader())
    reader = FakePathReader()
    service = RoutingService(topology, FakeController(), reader=reader)

    with pytest.raises(APIError) as error:
        service.path(src, dst)

    assert error.value.status_code == 404
    assert reader.calls == []


def test_routing_path_maps_missing_nodes_to_404() -> None:
    """A reader ValueError for a missing node is the common 404."""
    topology = TopologyService(_loaded_session(), FakeReader())
    reader = FakePathReader(error=ValueError("Node not found: Sat9"))
    service = RoutingService(topology, FakeController(), reader=reader)

    with pytest.raises(APIError) as error:
        service.path("Sat0", "Sat9")

    assert error.value.status_code == 404
    assert "Node not found" in error.value.message


def test_routing_path_maps_unexpected_reader_failures_to_500() -> None:
    """Unexpected reader failures are logged and surface as a 500."""
    topology = TopologyService(_loaded_session(), FakeReader())
    reader = FakePathReader(error=RuntimeError("graph exploded"))
    service = RoutingService(topology, FakeController(), reader=reader)

    with pytest.raises(APIError) as error:
        service.path("Sat0", "Sat1")

    assert error.value.status_code == 500


def test_routing_path_requires_a_project() -> None:
    """The path cannot be computed before a project is loaded."""
    topology = TopologyService(ProjectSession(), FakeReader())
    service = RoutingService(topology, FakeController(), reader=FakePathReader())

    with pytest.raises(APIError) as error:
        service.path("Sat0", "Sat1")

    assert error.value.status_code == 404


def test_routing_path_without_a_reader_is_a_500() -> None:
    """A service graph without a path reader fails explicitly."""
    topology = TopologyService(_loaded_session(), FakeReader())
    service = RoutingService(topology, FakeController())

    with pytest.raises(APIError) as error:
        service.path("Sat0", "Sat1")

    assert error.value.status_code == 500


def test_routing_apply_delete_and_stop_track_addressing() -> None:
    """Addressing is set only after apply and cleared by delete/stop."""
    topology = _ready_topology()
    controller = FakeController()
    service = RoutingService(topology, controller)

    asyncio.run(service.apply("static"))
    assert topology.addressing_applied is True
    assert service.status()["addressing_applied"] is True
    assert controller.calls == ["apply_addressing", "init_routing"]

    asyncio.run(service.delete())
    assert topology.addressing_applied is False
    assert service.status()["addressing_applied"] is False

    topology.set_addressing_applied(True)
    asyncio.run(service.stop_gonetem())
    assert topology.addressing_applied is False


def test_routing_apply_does_not_mark_a_replaced_project() -> None:
    """A project swap during apply must not write state onto the new session."""
    session = _loaded_session()
    topology = TopologyService(session, FakeReader(gonetem=True))
    started = threading.Event()
    release = threading.Event()

    class BlockingController(FakeController):
        def apply_addressing(self, target):
            started.set()
            release.wait(timeout=5)
            super().apply_addressing(target)

    service = RoutingService(topology, BlockingController())

    async def scenario() -> APIError:
        task = asyncio.create_task(service.apply("static"))
        await asyncio.to_thread(started.wait, 2)
        session.succeed(object(), "NewProject", "")
        release.set()
        with pytest.raises(APIError) as error:
            await task
        return error.value

    error = asyncio.run(scenario())

    assert error.status_code == 409
    assert "Project changed" in error.message
    assert session.project_name == "NewProject"
    assert session.addressing_applied is False


def test_routing_mutations_are_serialized() -> None:
    """Concurrent apply/delete/start/stop calls cannot overlap."""
    session = _loaded_session()
    topology = TopologyService(session, FakeReader(gonetem=True))
    started = threading.Event()
    release = threading.Event()
    active = 0
    max_active = 0

    class SerialController(FakeController):
        def apply_addressing(self, target):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            started.set()
            release.wait(timeout=5)
            super().apply_addressing(target)
            active -= 1

    service = RoutingService(topology, SerialController())

    async def scenario() -> None:
        first = asyncio.create_task(service.apply("static"))
        await asyncio.to_thread(started.wait, 2)
        second = asyncio.create_task(service.apply("static"))
        await asyncio.sleep(0.05)
        assert not second.done()
        release.set()
        await asyncio.gather(first, second)

    asyncio.run(scenario())

    assert max_active == 1


def test_cancelled_routing_operation_keeps_the_lock_until_the_worker_ends() -> None:
    """Cancellation must not let a second controller call overlap the worker."""
    topology = TopologyService(_loaded_session(), FakeReader(gonetem=True))
    started = threading.Event()
    release = threading.Event()
    active = 0
    max_active = 0

    class BlockingController(FakeController):
        def apply_addressing(self, target):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            started.set()
            release.wait(timeout=5)
            super().apply_addressing(target)
            active -= 1

    service = RoutingService(topology, BlockingController())

    async def scenario() -> None:
        first = asyncio.create_task(service.apply("static"))
        await asyncio.to_thread(started.wait, 2)
        first.cancel()
        await asyncio.sleep(0.05)
        second = asyncio.create_task(service.apply("static"))
        await asyncio.sleep(0.1)
        assert not second.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await first
        await second

    asyncio.run(scenario())

    assert max_active == 1


def test_routing_timeout_blocks_overlapping_operations_until_the_worker_ends() -> None:
    """A timed-out worker keeps its guard so a retry cannot overlap it."""
    topology = TopologyService(_loaded_session(), FakeReader(gonetem=True))
    release = threading.Event()

    class BlockingController(FakeController):
        def apply_addressing(self, target):
            release.wait(timeout=5)
            super().apply_addressing(target)

    service = RoutingService(
        topology,
        BlockingController(),
        operation_timeout_seconds=0.05,
    )

    async def scenario() -> None:
        with pytest.raises(APIError) as error:
            await service.apply("static")
        assert error.value.status_code == 504

        with pytest.raises(APIError) as conflict:
            await service.apply("static")
        assert conflict.value.status_code == 409

        release.set()
        await asyncio.sleep(0.1)
        await service.apply("static")

    asyncio.run(scenario())


def test_routing_start_is_blocked_while_a_project_operation_is_active() -> None:
    """Starting containers during a build cannot target the old topology."""
    session = _loaded_session()
    topology = TopologyService(session, FakeReader(gonetem=True))
    controller = FakeController()
    service = RoutingService(topology, controller)
    assert session.begin("NewProject", operation="create") is True

    with pytest.raises(APIError) as error:
        asyncio.run(service.start_gonetem())

    assert error.value.status_code == 409
    assert "project operation" in error.value.message.lower()
    assert "start_gonetem" not in controller.calls


def test_routing_status_does_not_use_gonetem_as_addressing() -> None:
    """A running container network does not imply addressing was applied."""
    topology = TopologyService(_loaded_session(), FakeReader(gonetem=True))
    service = RoutingService(topology, FakeController())

    assert service.status()["gonetem_is_on"] is True
    assert service.status()["addressing_applied"] is False


def test_routing_init_failure_keeps_addressing_state_truthful() -> None:
    """Addressing can succeed before routing initialization fails."""
    topology = _ready_topology()
    service = RoutingService(topology, FakeController(fail_init=True))

    with pytest.raises(APIError) as error:
        asyncio.run(service.apply("static"))

    assert error.value.status_code == 500
    assert topology.addressing_applied is True


class FailingController(FakeController):
    """Controller with configurable operation failures."""

    def __init__(self, failure: str) -> None:
        super().__init__()
        self.failure = failure

    def apply_addressing(self, topology):
        if self.failure == "addressing":
            raise NetworkOperationError("addressing failed")
        super().apply_addressing(topology)

    def delete_routing(self, topology):
        if self.failure == "delete":
            raise NetworkOperationError("delete failed")
        super().delete_routing(topology)

    def start_gonetem(self, topology):
        if self.failure == "start":
            raise NetworkOperationError("start failed")
        super().start_gonetem(topology)

    def stop_gonetem(self, topology):
        if self.failure == "stop":
            raise NetworkOperationError("stop failed")
        super().stop_gonetem(topology)


def test_routing_addressing_failure_maps_500() -> None:
    """A failed addressing step is reported without marking addressing applied."""
    topology = TopologyService(_loaded_session(), FakeReader(gonetem=True))
    service = RoutingService(topology, FailingController("addressing"))

    with pytest.raises(APIError) as error:
        asyncio.run(service.apply("static"))

    assert error.value.status_code == 500
    assert topology.addressing_applied is False


def test_routing_delete_failure_maps_500() -> None:
    """A failed delete is reported and leaves address state unchanged."""
    topology = _ready_topology()
    topology.set_addressing_applied(True)
    service = RoutingService(topology, FailingController("delete"))

    with pytest.raises(APIError) as error:
        asyncio.run(service.delete())

    assert error.value.status_code == 500
    assert topology.addressing_applied is True


def test_routing_start_failure_maps_500() -> None:
    """A failed container start is reported."""
    topology = _ready_topology()
    service = RoutingService(topology, FailingController("start"))

    with pytest.raises(APIError) as error:
        asyncio.run(service.start_gonetem())

    assert error.value.status_code == 500


def test_routing_stop_failure_keeps_addressing() -> None:
    """A failed stop is reported and does not clear address state."""
    topology = _ready_topology()
    topology.set_addressing_applied(True)
    service = RoutingService(topology, FailingController("stop"))

    with pytest.raises(APIError) as error:
        asyncio.run(service.stop_gonetem())

    assert error.value.status_code == 500
    assert topology.addressing_applied is True
