"""Unit tests for service orchestration with fake gateways."""

import asyncio
import threading
import time

import pytest

from satgonetem_gui.config import Settings
from satgonetem_gui.errors import APIError
from satgonetem_gui.schemas import Iperf3Request, PingRequest, ProjectCreateRequest
from satgonetem_gui.services.ports import NetworkOperationError, TrafficPoll
from satgonetem_gui.services.project_service import ProjectService
from satgonetem_gui.services.routing_service import RoutingService
from satgonetem_gui.services.topology_service import TopologyService
from satgonetem_gui.services.traffic_service import (
    JobCapacityError,
    JobRegistry,
    TrafficJob,
    TrafficService,
)
from satgonetem_gui.state import ProjectSession, ProjectState, RuntimeState
from tests.factories import project_payload


class FakeReader:
    """Minimal topology reader for service tests."""

    def __init__(self, gonetem: bool = False) -> None:
        self.gonetem = gonetem

    def status(self, topology):
        return {
            "constellation_loaded": True,
            "satellites": 1,
            "ground_stations": 0,
            "links": 0,
            "gonetem_is_on": self.gonetem,
            "simulation_updating": False,
            "current_step": 0,
            "current_time": None,
        }

    def satellites(self, topology):
        return [{"id": 0, "name": "Sat0", "position": {}}]

    def traffic_nodes(self, topology):
        return [{"name": "Sat0", "type": "satellite"}]

    def find_node(self, topology, name):
        return name if name == "Sat0" else None

    def gonetem_is_on(self, topology):
        return self.gonetem


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


class FakeTraffic:
    """Minimal traffic gateway for service tests."""

    def __init__(self, poll_status: str = "done") -> None:
        self.poll_status = poll_status
        self.stopped = []
        self.poll_calls = 0

    def start_iperf3(self, source, destination, request):
        return object()

    def start_ping(self, source, destination, request):
        return object()

    def start_hping3(self, source, destination, request):
        return object()

    def poll(self, kind, flow):
        self.poll_calls += 1
        if self.poll_status == "done":
            return TrafficPoll("done", results={"ok": True})
        return TrafficPoll(self.poll_status)

    def stop(self, flow):
        self.stopped.append(flow)


def _loaded_session() -> ProjectSession:
    session = ProjectSession()
    session.succeed(object(), "Project", "")
    return session


def _ready_topology() -> TopologyService:
    """Return a loaded topology with addressing applied for traffic tests."""
    topology = TopologyService(_loaded_session(), FakeReader(gonetem=True))
    topology.set_addressing_applied(True)
    return topology


def test_topology_status_is_empty_without_a_project() -> None:
    """The dashboard can read an empty status before a project is loaded."""
    service = TopologyService(ProjectSession(), FakeReader())

    assert service.status()["constellation_loaded"] is False
    assert service.status()["satellites"] == 0


def test_topology_queries_require_a_project() -> None:
    """Read routes raise the common 404 when nothing is loaded."""
    service = TopologyService(ProjectSession(), FakeReader())

    with pytest.raises(APIError) as error:
        service.satellites()

    assert error.value.status_code == 404


def test_routing_apply_requires_gonetem() -> None:
    """Routing is rejected while the containers are stopped."""
    session = _loaded_session()
    topology = TopologyService(session, FakeReader(gonetem=False))
    service = RoutingService(topology, FakeController())

    with pytest.raises(APIError) as error:
        asyncio.run(service.apply("static"))

    assert error.value.status_code == 409


def test_traffic_requires_a_project() -> None:
    """Traffic cannot start before a project is loaded."""
    topology = TopologyService(ProjectSession(), FakeReader())
    service = TrafficService(topology, FakeTraffic())

    with pytest.raises(APIError) as error:
        service.start("iperf3", Iperf3Request(src="Sat0", dst="Sat0"))

    assert error.value.status_code == 404


def test_traffic_requires_gonetem() -> None:
    """Traffic cannot start while the containers are stopped."""
    topology = TopologyService(_loaded_session(), FakeReader(gonetem=False))
    service = TrafficService(topology, FakeTraffic())

    with pytest.raises(APIError) as error:
        service.start("iperf3", Iperf3Request(src="Sat0", dst="Sat0"))

    assert error.value.status_code == 409


def test_traffic_requires_addressing() -> None:
    """Traffic cannot start before container interfaces are addressed."""
    topology = TopologyService(_loaded_session(), FakeReader(gonetem=True))
    service = TrafficService(topology, FakeTraffic())

    with pytest.raises(APIError) as error:
        service.start("iperf3", Iperf3Request(src="Sat0", dst="Sat0"))

    assert error.value.status_code == 409
    assert "addressing" in error.value.message.lower()


def test_traffic_rejects_unknown_kind() -> None:
    """Only registered flow strategies can be started."""
    topology = _ready_topology()
    service = TrafficService(topology, FakeTraffic())

    with pytest.raises(APIError) as error:
        service.start("unknown", Iperf3Request(src="Sat0", dst="Sat0"))

    assert error.value.status_code == 400


def test_traffic_start_and_status() -> None:
    """A started job is polled through the one status path."""
    topology = _ready_topology()
    gateway = FakeTraffic()
    service = TrafficService(topology, gateway)

    job_id = service.start("ping", PingRequest(src="Sat0", dst="Sat0"))

    assert job_id.startswith("j")
    assert service.status(job_id) == {"status": "done", "results": {"ok": True}}
    assert gateway.poll_calls == 1


def test_traffic_cancel_stops_flow_and_stays_cancelled() -> None:
    """Cancel polls once, calls stop, and avoids future polling."""
    topology = _ready_topology()
    gateway = FakeTraffic(poll_status="running")
    service = TrafficService(topology, gateway)
    job_id = service.start("ping", PingRequest(src="Sat0", dst="Sat0"))
    job = service.jobs.get(job_id)

    service.cancel(job_id)

    assert job is not None
    assert job.status == "cancelled"
    assert gateway.stopped == [job.flow]
    assert gateway.poll_calls == 1
    assert service.status(job_id) == {"status": "cancelled"}
    assert gateway.poll_calls == 1


def test_cancel_before_poll_preserves_completed_results() -> None:
    """Cancel polls first so a finished flow keeps its results."""
    topology = _ready_topology()
    gateway = FakeTraffic(poll_status="done")
    service = TrafficService(topology, gateway)
    job_id = service.start("ping", PingRequest(src="Sat0", dst="Sat0"))
    job = service.jobs.get(job_id)

    with pytest.raises(APIError) as error:
        service.cancel(job_id)

    assert error.value.status_code == 409
    assert error.value.message == "Job is already finished."
    assert job is not None
    assert job.status == "done"
    assert job.results == {"ok": True}
    assert gateway.poll_calls >= 1
    assert gateway.stopped == []


def test_cancel_poll_failure_does_not_discard_an_unverified_job() -> None:
    """If the state cannot be verified, leave the job running for a retry."""
    topology = _ready_topology()
    gateway = FakeTraffic(poll_status="running")

    def fail_poll(_kind, _flow):
        raise RuntimeError("poll failed")

    gateway.poll = fail_poll
    service = TrafficService(topology, gateway)
    job_id = service.start("ping", PingRequest(src="Sat0", dst="Sat0"))
    job = service.jobs.get(job_id)

    with pytest.raises(APIError) as error:
        service.cancel(job_id)

    assert error.value.status_code == 500
    assert "retry cancel" in error.value.message
    assert job is not None
    assert job.status == "running"
    assert gateway.stopped == []


def test_traffic_cancel_failure_keeps_job_running() -> None:
    """A failed stop is reported and does not fake a cancellation."""
    topology = _ready_topology()
    gateway = FakeTraffic(poll_status="running")

    def fail(_flow):
        raise RuntimeError("stop failed")

    gateway.stop = fail
    service = TrafficService(topology, gateway)
    job_id = service.start("ping", PingRequest(src="Sat0", dst="Sat0"))

    with pytest.raises(APIError) as error:
        service.cancel(job_id)

    assert error.value.status_code == 500
    assert service.jobs.get(job_id).status == "running"


def test_cancel_finished_job_returns_conflict() -> None:
    """Finished jobs are terminal and cannot be cancelled."""
    topology = _ready_topology()
    service = TrafficService(topology, FakeTraffic())
    job_id = service.start("ping", PingRequest(src="Sat0", dst="Sat0"))
    service.status(job_id)

    with pytest.raises(APIError) as error:
        service.cancel(job_id)

    assert error.value.status_code == 409


def test_job_terminal_transitions_are_immutable() -> None:
    """A terminal job cannot transition again."""
    job = TrafficJob(job_id="j1", kind="ping", flow=object(), src="a", dst="b")

    assert job.transition("done", results={"ok": True}) is True
    assert job.transition("error", error="late") is False
    assert job.snapshot() == {"status": "done", "results": {"ok": True}}


def test_registry_enforces_max_jobs() -> None:
    """The registry rejects a new job when all slots belong to running jobs."""
    registry = JobRegistry(max_jobs=1)
    registry.create("ping", object(), "a", "b")

    with pytest.raises(JobCapacityError):
        registry.create("ping", object(), "a", "b")


def test_registry_evicts_finished_jobs_when_full() -> None:
    """Finished jobs release capacity before a new job is rejected."""
    registry = JobRegistry(max_jobs=1)
    first = registry.create("ping", object(), "a", "b")
    first.transition("done")

    second = registry.create("ping", object(), "a", "b")

    assert registry.get(first.job_id) is None
    assert registry.get(second.job_id) is second


def test_registry_prunes_expired_terminal_jobs() -> None:
    """Terminal jobs older than the TTL are removed."""
    now = 0.0
    registry = JobRegistry(max_jobs=10, ttl_seconds=10, clock=lambda: now)
    job = registry.create("ping", object(), "a", "b")
    job.transition("done")
    now = 100.0

    registry.prune()

    assert registry.get(job.job_id) is None


def test_capacity_rejection_stops_the_unregistered_flow() -> None:
    """A running job keeps its slot, so the unregistered flow is stopped."""
    topology = _ready_topology()
    gateway = FakeTraffic(poll_status="running")
    jobs = JobRegistry(max_jobs=1)
    jobs.create("ping", object(), "a", "b")
    service = TrafficService(topology, gateway, jobs)

    with pytest.raises(APIError) as error:
        service.start("ping", PingRequest(src="Sat0", dst="Sat0"))

    assert error.value.status_code == 429
    assert gateway.poll_calls == 1
    assert len(gateway.stopped) == 1


def test_registration_failure_stops_the_unregistered_flow() -> None:
    """Any registry failure, not only capacity, cleans up the started flow."""

    class BrokenRegistry:
        def create(self, *_args, **_kwargs):
            raise RuntimeError("registry unavailable")

        def running(self):
            return []

    topology = _ready_topology()
    gateway = FakeTraffic()
    service = TrafficService(topology, gateway, BrokenRegistry())

    with pytest.raises(APIError) as error:
        service.start("ping", PingRequest(src="Sat0", dst="Sat0"))

    assert error.value.status_code == 500
    assert len(gateway.stopped) == 1


def test_lazy_reclaim_polls_finished_jobs_when_the_registry_is_full() -> None:
    """A full registry polls running jobs once and retries job creation."""
    topology = _ready_topology()
    gateway = FakeTraffic(poll_status="done")
    registry = JobRegistry(max_jobs=1)
    service = TrafficService(topology, gateway, registry)

    first_id = service.start("ping", PingRequest(src="Sat0", dst="Sat0"))
    second_id = service.start("ping", PingRequest(src="Sat0", dst="Sat0"))

    assert first_id != second_id
    assert registry.get(first_id) is None
    assert registry.get(second_id) is not None
    assert gateway.poll_calls == 1
    assert gateway.stopped == []


def test_traffic_service_preserves_an_injected_empty_registry() -> None:
    """An empty registry is falsy but must not be replaced by the service."""
    topology = _ready_topology()
    registry = JobRegistry(max_jobs=1)

    service = TrafficService(topology, FakeTraffic(), registry)

    assert service.jobs is registry
    assert service.jobs.max_jobs == 1


def test_status_treats_an_unknown_gateway_state_as_a_terminal_error() -> None:
    """An unrecognized poll state becomes a terminal error, not 'unknown'."""
    topology = _ready_topology()
    gateway = FakeTraffic(poll_status="unknown")
    service = TrafficService(topology, gateway)
    job_id = service.start("ping", PingRequest(src="Sat0", dst="Sat0"))

    result = service.status(job_id)

    assert result == {"status": "error", "error": "Unknown flow state."}
    assert service.jobs.get(job_id).terminal is True
    assert service.status(job_id) == result
    assert gateway.poll_calls == 1


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


def test_registry_running_returns_a_snapshot_of_active_jobs() -> None:
    """Only non-terminal jobs are returned for lazy reclaim."""
    registry = JobRegistry()
    running = registry.create("ping", object(), "a", "b")
    finished = registry.create("ping", object(), "a", "b")
    finished.transition("done")

    assert registry.running() == [running]


def test_strategy_registry_covers_all_tools() -> None:
    """The registry exposes exactly the typed traffic strategies."""
    from satgonetem_gui.schemas import Hping3Request

    topology = _ready_topology()
    service = TrafficService(topology, FakeTraffic())

    assert set(service.strategies) == {"iperf3", "ping", "hping3"}
    assert service.strategies["iperf3"].request_type is Iperf3Request
    assert service.strategies["ping"].request_type is PingRequest
    assert service.strategies["hping3"].request_type is Hping3Request


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


def test_status_stays_loaded_after_containers_stop() -> None:
    """Project availability is independent of container status."""
    session = _loaded_session()

    class StoppedReader(FakeReader):
        def status(self, topology):
            data = super().status(topology)
            data["constellation_loaded"] = False
            return data

    service = TopologyService(session, StoppedReader())

    assert service.status()["constellation_loaded"] is True


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
