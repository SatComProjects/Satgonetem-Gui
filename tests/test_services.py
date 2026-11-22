"""Unit tests for service orchestration with fake gateways."""

import asyncio
import hashlib
import json
import threading
import time

import pytest

from satgonetem_gui.config import Settings
from satgonetem_gui.errors import APIError
from satgonetem_gui.schemas import (
    ConnectivityStartRequest,
    ExperimentStartRequest,
    Iperf3Request,
    PingRequest,
    ProjectCreateRequest,
)
from satgonetem_gui.services import connectivity_service
from satgonetem_gui.services.addressability_service import AddressabilityService
from satgonetem_gui.services.connectivity_service import (
    ConnectivityJobRegistry,
    ConnectivityService,
)
from satgonetem_gui.services.experiment_service import ExperimentService
from satgonetem_gui.services.ports import NetworkOperationError, TrafficPoll
from satgonetem_gui.services.project_service import ProjectService
from satgonetem_gui.services.routing_service import RoutingService
from satgonetem_gui.services.simulation_service import SimulationService
from satgonetem_gui.services.topology_service import TopologyService
from satgonetem_gui.services.traffic_service import (
    JobCapacityError,
    JobRegistry,
    TrafficJob,
    TrafficService,
)
from satgonetem_gui.state import ProjectResult, ProjectSession, ProjectState, RuntimeState
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


class FakeUsageReader:
    """Minimal link-usage reader for service tests."""

    def __init__(self, response=None) -> None:
        self.response = response or {
            "available": True,
            "sampled_at": "2024-01-01T00:00:00+00:00",
            "links": [],
            "note": None,
        }
        self.calls = []

    def link_usage(self, topology):
        self.calls.append(topology)
        return self.response


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


class FakeTraffic:
    """Minimal traffic gateway for service tests."""

    def __init__(self, poll_status: str = "done") -> None:
        self.poll_status = poll_status
        self.stopped = []
        self.released = []
        self.registered = []
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

    def release(self, flow):
        self.released.append(flow)

    def register_flow(self, topology, flow):
        self.registered.append(flow)


def _loaded_session() -> ProjectSession:
    session = ProjectSession()
    session.succeed(object(), "Project", "")
    return session


def _ready_topology() -> TopologyService:
    """Return a loaded topology with addressing applied for traffic tests."""
    topology = TopologyService(_loaded_session(), FakeReader(gonetem=True))
    topology.set_addressing_applied(True)
    return topology


def _simulation_service(
    controller: FakeSimulationController | None = None,
    session: ProjectSession | None = None,
) -> tuple[SimulationService, FakeSimulationController]:
    """Return a simulation service with a fake controller."""
    session = session if session is not None else _loaded_session()
    controller = controller if controller is not None else FakeSimulationController()
    topology = TopologyService(session, FakeReader())
    return SimulationService(topology, controller), controller


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


def test_topology_status_is_empty_without_a_project() -> None:
    """The dashboard can read an empty status before a project is loaded."""
    service = TopologyService(ProjectSession(), FakeReader())

    assert service.status()["constellation_loaded"] is False
    assert service.status()["satellites"] == 0


def test_topology_context_returns_the_topology_and_generation_together() -> None:
    """Routing reads both values from one session snapshot."""
    session = _loaded_session()
    service = TopologyService(session, FakeReader())

    topology, generation = service.context()

    assert topology is session.get_topology()
    assert generation == session.generation


def test_topology_queries_require_a_project() -> None:
    """Read routes raise the common 404 when nothing is loaded."""
    service = TopologyService(ProjectSession(), FakeReader())

    with pytest.raises(APIError) as error:
        service.satellites()

    assert error.value.status_code == 404


def test_topology_link_usage_requires_a_project() -> None:
    """Usage cannot be sampled before a project is loaded."""
    reader = FakeUsageReader()
    service = TopologyService(ProjectSession(), FakeReader(), usage_reader=reader)

    with pytest.raises(APIError) as error:
        service.link_usage()

    assert error.value.status_code == 404
    assert reader.calls == []


def test_topology_link_usage_returns_the_reader_payload() -> None:
    """The service forwards the installed topology to the usage reader."""
    session = _loaded_session()
    reader = FakeUsageReader()
    service = TopologyService(session, FakeReader(), usage_reader=reader)

    result = service.link_usage()

    assert result is reader.response
    assert reader.calls == [session.get_topology()]


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
    job = service.jobs.get(job_id)
    flow = job.flow

    assert job_id.startswith("j")
    assert gateway.registered == [flow]
    assert service.status(job_id) == {"status": "done", "results": {"ok": True}}
    assert gateway.poll_calls == 1
    assert job.flow is None
    assert gateway.released == [flow]


def test_job_is_discarded_when_the_project_is_replaced() -> None:
    """A job from the old topology cannot keep polling or showing results."""
    topology = _ready_topology()
    gateway = FakeTraffic(poll_status="running")
    service = TrafficService(topology, gateway)
    job_id = service.start("ping", PingRequest(src="Sat0", dst="Sat0"))
    job = service.jobs.get(job_id)
    flow = job.flow
    topology.session.succeed(object(), "NewProject", "")

    result = service.status(job_id)

    assert result["status"] == "error"
    assert "Project changed" in result["error"]
    assert job.flow is None
    assert gateway.released == [flow]


def test_traffic_cancel_stops_flow_and_stays_cancelled() -> None:
    """Cancel polls once, calls stop, and avoids future polling."""
    topology = _ready_topology()
    gateway = FakeTraffic(poll_status="running")
    service = TrafficService(topology, gateway)
    job_id = service.start("ping", PingRequest(src="Sat0", dst="Sat0"))
    job = service.jobs.get(job_id)
    flow = job.flow

    service.cancel(job_id)

    assert job is not None
    assert job.status == "cancelled"
    assert gateway.stopped == [flow]
    assert gateway.released == [flow]
    assert job.flow is None
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


def test_registry_prune_does_not_wait_for_a_job_lock() -> None:
    """A slow status/cancel call must not stall unrelated registry work."""
    registry = JobRegistry()
    job = registry.create("ping", object(), "a", "b")
    job.lock.acquire()
    completed = threading.Event()

    def prune() -> None:
        registry.prune()
        completed.set()

    thread = threading.Thread(target=prune)
    try:
        thread.start()
        assert completed.wait(1.0)
    finally:
        job.lock.release()
        thread.join(timeout=2)


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


class FakeAddressabilityController:
    """In-memory satellite addressability controller for service tests."""

    def __init__(
        self,
        total: int = 3,
        addressable: set[str] | None = None,
        failure: str | None = None,
        on_set=None,
    ) -> None:
        self.names = [f"Sat{index}" for index in range(total)]
        self.addressable_names = set(addressable or ())
        self.failure = failure
        self.on_set = on_set
        self.calls: list = []

    def satellite_addressability(self, topology):
        self.calls.append("status")
        return {
            "addressable": sorted(self.addressable_names),
            "total": len(self.names),
        }

    def set_satellites_addressable(self, topology, enabled, names=None):
        self.calls.append(("set", enabled, names))
        if self.failure == "network":
            raise NetworkOperationError("addressability failed")
        if self.failure == "unexpected":
            raise RuntimeError("controller exploded")
        targets = self.names if names is None else list(names)
        for name in targets:
            if name not in self.names:
                raise ValueError(f"Unknown satellite: {name}")
        for name in targets:
            if enabled:
                self.addressable_names.add(name)
            else:
                self.addressable_names.discard(name)
        if self.on_set is not None:
            self.on_set()
        return len(targets)


def _addressability_service(
    controller: FakeAddressabilityController | None = None,
    session: ProjectSession | None = None,
) -> tuple[AddressabilityService, FakeAddressabilityController]:
    """Return an addressability service with a fake controller."""
    session = session if session is not None else _loaded_session()
    controller = controller if controller is not None else FakeAddressabilityController()
    topology = TopologyService(session, FakeReader())
    return AddressabilityService(topology, controller), controller


def test_addressability_status_reports_sorted_names_and_counts() -> None:
    """Status lists the addressable satellites with count and total."""
    controller = FakeAddressabilityController(
        total=3,
        addressable={"Sat2", "Sat0"},
    )
    service, _ = _addressability_service(controller)

    assert service.status() == {
        "ok": True,
        "addressable": ["Sat0", "Sat2"],
        "count": 2,
        "total": 3,
        "routing_refresh_required": False,
    }

    service.topology.set_addressing_applied(True)
    assert service.status()["routing_refresh_required"] is True


def test_addressability_status_requires_a_project() -> None:
    """Status cannot be read before a project is loaded."""
    topology = TopologyService(ProjectSession(), FakeReader())
    service = AddressabilityService(topology, FakeAddressabilityController())

    with pytest.raises(APIError) as error:
        service.status()

    assert error.value.status_code == 404


def test_addressability_global_toggle_enables_and_disables_every_satellite() -> None:
    """The global toggle dispatches one unqualified controller call."""
    service, controller = _addressability_service()

    enabled = service.set_all(True)

    assert enabled == {
        "ok": True,
        "enabled": True,
        "updated": 3,
        "routing_refresh_required": False,
    }
    assert controller.calls == [("set", True, None)]
    assert service.topology.session.network_operation is False
    assert service.status()["count"] == 3
    assert controller.calls == [("set", True, None), "status"]

    disabled = service.set_all(False)

    assert disabled["enabled"] is False
    assert disabled["updated"] == 3
    assert controller.calls[-1] == ("set", False, None)
    assert service.status()["count"] == 0


def test_addressability_per_node_toggle_updates_one_satellite() -> None:
    """The per-node toggle reports the node and its new addressability."""
    service, controller = _addressability_service()

    result = service.set_one("Sat1", True)

    assert result == {
        "ok": True,
        "name": "Sat1",
        "addressable": True,
        "enabled": True,
        "updated": 1,
        "routing_refresh_required": False,
    }
    assert controller.calls == [("set", True, ["Sat1"])]
    assert service.topology.session.network_operation is False
    assert service.status()["addressable"] == ["Sat1"]


@pytest.mark.parametrize("name", ["Gnd100", "Satellite", "Sat", "Sat-1"])
def test_addressability_rejects_malformed_names_before_dispatch(name: str) -> None:
    """Only the core's satellite name form reaches the controller."""
    service, controller = _addressability_service()

    with pytest.raises(APIError) as error:
        service.set_one(name, True)

    assert error.value.status_code == 404
    assert controller.calls == []
    assert service.topology.session.network_operation is False


def test_addressability_missing_satellite_maps_to_404() -> None:
    """A satellite name the adapter cannot resolve is a client error."""
    service, controller = _addressability_service(FakeAddressabilityController(total=3))

    with pytest.raises(APIError) as error:
        service.set_one("Sat404", True)

    assert error.value.status_code == 404
    assert "Unknown satellite: Sat404" in error.value.message
    assert service.topology.session.network_operation is False


def test_addressability_rejects_an_in_flight_network_operation() -> None:
    """An addressability mutation cannot overlap routing/container work."""
    service, controller = _addressability_service()
    assert service.topology.session.begin_network_operation() is True
    try:
        with pytest.raises(APIError) as error:
            service.set_all(True)
    finally:
        service.topology.session.end_network_operation()

    assert error.value.status_code == 409
    assert "project operation" in error.value.message.lower()
    assert controller.calls == []


def test_addressability_rejects_a_project_changed_mid_operation() -> None:
    """A mutation must not report success on a replaced project."""
    session = _loaded_session()

    def replace_project() -> None:
        session.succeed(object(), "NewProject", "")

    controller = FakeAddressabilityController(on_set=replace_project)
    service, _ = _addressability_service(controller, session)

    with pytest.raises(APIError) as error:
        service.set_all(True)

    assert error.value.status_code == 409
    assert "Project changed" in error.value.message
    assert session.network_operation is False


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        ("network", "addressability failed"),
        ("unexpected", "Failed to update satellite addressability."),
    ],
)
def test_addressability_controller_failures_map_to_500(failure: str, message: str) -> None:
    """Controller failures are reported without leaking a traceback."""
    service, _ = _addressability_service(FakeAddressabilityController(failure=failure))

    with pytest.raises(APIError) as error:
        service.set_all(True)

    assert error.value.status_code == 500
    assert message in error.value.message
    assert service.topology.session.network_operation is False


def test_addressability_mutations_report_routing_refresh_after_the_update() -> None:
    """Both toggles report the addressing state after the change."""
    service, _ = _addressability_service()
    service.topology.set_addressing_applied(True)

    assert service.set_one("Sat1", True)["routing_refresh_required"] is True
    assert service.set_all(False)["routing_refresh_required"] is True
    assert service.status()["routing_refresh_required"] is True


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


class FakeConnectivityController:
    """Minimal connectivity controller for service tests."""

    def __init__(
        self,
        result: dict | None = None,
        error: Exception | None = None,
        resolver=None,
    ) -> None:
        self.result = result if result is not None else _matrix_result()
        self.error = error
        self.resolver = resolver
        self.resolved: list[list[str] | None] = []
        self.calls: list[dict] = []

    def resolve_connectivity_nodes(self, topology, names):
        self.resolved.append(names)
        if self.resolver is not None:
            return self.resolver(names)
        return list(names) if names is not None else ["Sat0", "Sat1"]

    def run_connectivity_matrix(
        self,
        topology,
        names,
        *,
        ping_count,
        max_workers,
        flow_timeout_seconds,
    ):
        self.calls.append(
            {
                "names": list(names),
                "ping_count": ping_count,
                "max_workers": max_workers,
                "flow_timeout_seconds": flow_timeout_seconds,
            }
        )
        if self.error is not None:
            raise self.error
        return self.result


def _matrix_result() -> dict:
    """Return a complete connectivity matrix payload for pass-through tests."""
    return {
        "nodes": ["Sat0", "Sat1"],
        "summary": {"pairs": 2, "reachable": 1, "unreachable": 1},
        "results": [
            {
                "source": "Sat0",
                "destination": "Sat1",
                "reachable": True,
                "packets_transmitted": 3,
                "packets_received": 3,
                "packet_loss_percent": 0.0,
                "rtt_min_ms": 1.0,
                "rtt_avg_ms": 1.5,
                "rtt_max_ms": 2.0,
                "error": None,
            },
            {
                "source": "Sat1",
                "destination": "Sat0",
                "reachable": False,
                "packets_transmitted": 3,
                "packets_received": 0,
                "packet_loss_percent": 100.0,
                "rtt_min_ms": None,
                "rtt_avg_ms": None,
                "rtt_max_ms": None,
                "error": "no reply",
            },
        ],
    }


def _connectivity_payload(**overrides) -> ConnectivityStartRequest:
    """Return a valid connectivity request with overridable fields."""
    values = {
        "nodes": ["Sat0", "Sat1"],
        "ping_count": 3,
        "max_workers": 4,
        "flow_timeout_seconds": 5.0,
    }
    values.update(overrides)
    return ConnectivityStartRequest(**values)


def _wait_for_connectivity(
    service: ConnectivityService,
    job_id: str,
    timeout: float = 2.0,
) -> dict:
    """Poll a connectivity job until it reaches a terminal state."""
    deadline = time.monotonic() + timeout
    status = service.status(job_id)
    while status["status"] == "running" and time.monotonic() < deadline:
        time.sleep(0.005)
        status = service.status(job_id)
    return status


def test_connectivity_requires_a_project() -> None:
    """A connectivity check cannot start before a project is loaded."""
    topology = TopologyService(ProjectSession(), FakeReader())
    service = ConnectivityService(topology, FakeConnectivityController())

    with pytest.raises(APIError) as error:
        service.start(_connectivity_payload())

    assert error.value.status_code == 404


def test_connectivity_requires_running_containers() -> None:
    """A connectivity check requires started GoNetEm containers."""
    topology = TopologyService(_loaded_session(), FakeReader(gonetem=False))
    service = ConnectivityService(topology, FakeConnectivityController())

    with pytest.raises(APIError) as error:
        service.start(_connectivity_payload())

    assert error.value.status_code == 409
    assert "GoNetEm" in error.value.message


def test_connectivity_requires_applied_addressing() -> None:
    """A connectivity check requires addressing to be applied first."""
    topology = TopologyService(_loaded_session(), FakeReader(gonetem=True))
    service = ConnectivityService(topology, FakeConnectivityController())

    with pytest.raises(APIError) as error:
        service.start(_connectivity_payload())

    assert error.value.status_code == 409
    assert "addressing" in error.value.message.lower()


def test_connectivity_maps_resolution_errors_to_422() -> None:
    """An invalid node selection is a client error before a job is reserved."""
    controller = FakeConnectivityController(
        resolver=lambda _names: (_ for _ in ()).throw(
            ValueError("Node is not an addressable traffic endpoint: Missing")
        )
    )
    service = ConnectivityService(_ready_topology(), controller)

    with pytest.raises(APIError) as error:
        service.start(_connectivity_payload(nodes=["Missing", "Sat0"]))

    assert error.value.status_code == 422
    assert "Missing" in error.value.message
    assert len(service.jobs) == 0


def test_connectivity_rejects_fewer_than_two_nodes() -> None:
    """A matrix needs two distinct endpoints."""
    controller = FakeConnectivityController(resolver=lambda _names: ["Sat0"])
    service = ConnectivityService(_ready_topology(), controller)

    with pytest.raises(APIError) as error:
        service.start(_connectivity_payload(nodes=["Sat0"]))

    assert error.value.status_code == 422
    assert "two" in error.value.message.lower()


def test_connectivity_rejects_more_than_32_nodes() -> None:
    """The node cap protects the GUI and the emulation from huge matrices."""
    controller = FakeConnectivityController(
        resolver=lambda _names: [f"Sat{index}" for index in range(33)]
    )
    service = ConnectivityService(_ready_topology(), controller)

    with pytest.raises(APIError) as error:
        service.start(_connectivity_payload(nodes=None))

    assert error.value.status_code == 422
    assert "32" in error.value.message


def test_connectivity_rejects_more_than_2000_pairs(monkeypatch) -> None:
    """The ordered-pair cap is enforced independently of the node cap."""
    monkeypatch.setattr(connectivity_service, "MAX_NODES", 50)
    controller = FakeConnectivityController(
        resolver=lambda _names: [f"Sat{index}" for index in range(46)]
    )
    service = ConnectivityService(_ready_topology(), controller)

    with pytest.raises(APIError) as error:
        service.start(_connectivity_payload(nodes=None))

    assert error.value.status_code == 422
    assert "2000" in error.value.message
    assert len(service.jobs) == 0


def test_connectivity_start_and_status_done() -> None:
    """A started job runs the controller and exposes its completed matrix."""
    topology = _ready_topology()
    controller = FakeConnectivityController()
    service = ConnectivityService(topology, controller)

    job_id = service.start(_connectivity_payload())

    assert job_id.startswith("c")
    status = _wait_for_connectivity(service, job_id)
    assert status["status"] == "done", status
    assert status["job_id"] == job_id
    assert status["nodes"] == ["Sat0", "Sat1"]
    assert status["pair_count"] == 2
    assert status["summary"] == {
        "pairs": 2,
        "reachable": 1,
        "unreachable": 1,
    }
    assert [item["source"] for item in status["results"]] == ["Sat0", "Sat1"]
    assert status["started_at"] is not None
    assert status["finished_at"] is not None
    assert status["elapsed_ms"] >= 0
    assert status["error"] is None
    assert controller.calls == [
        {
            "names": ["Sat0", "Sat1"],
            "ping_count": 3,
            "max_workers": 4,
            "flow_timeout_seconds": 5.0,
        }
    ]


def test_connectivity_status_reports_a_safe_worker_error() -> None:
    """A worker failure becomes a terminal, user-facing error."""
    controller = FakeConnectivityController(error=RuntimeError("matrix exploded"))
    service = ConnectivityService(_ready_topology(), controller)
    job_id = service.start(_connectivity_payload())

    status = _wait_for_connectivity(service, job_id)

    assert status["status"] == "error"
    assert "matrix exploded" in status["error"]
    assert status["summary"] is None
    assert status["results"] == []
    assert status["finished_at"] is not None


def test_connectivity_rejects_an_invalid_matrix_result() -> None:
    """A controller payload without a summary is a failed job, not a 500."""
    controller = FakeConnectivityController(result={"results": []})
    service = ConnectivityService(_ready_topology(), controller)
    job_id = service.start(_connectivity_payload())

    status = _wait_for_connectivity(service, job_id)

    assert status["status"] == "error"
    assert "invalid result" in status["error"]


def test_connectivity_job_is_discarded_when_the_project_is_replaced() -> None:
    """A result from a replaced project is never reported as success."""
    topology = _ready_topology()
    controller = FakeConnectivityController()

    def replace_project(topology_arg, names, **kwargs):
        result = _matrix_result()
        topology.session.succeed(object(), "NewProject", "")
        return result

    controller.run_connectivity_matrix = replace_project
    service = ConnectivityService(topology, controller)
    job_id = service.start(_connectivity_payload())

    status = _wait_for_connectivity(service, job_id)

    assert status["status"] == "error"
    assert "Project changed" in status["error"]


def test_connectivity_unknown_job_is_404() -> None:
    """Unknown job ids are normal 404s for status and export."""
    service = ConnectivityService(_ready_topology(), FakeConnectivityController())

    with pytest.raises(APIError) as status_error:
        service.status("missing")
    with pytest.raises(APIError) as export_error:
        service.export("missing", "csv")

    assert status_error.value.status_code == 404
    assert export_error.value.status_code == 404


def test_connectivity_export_csv_for_a_done_job() -> None:
    """Done jobs export CSV with the documented header and boolean casing."""
    service = ConnectivityService(_ready_topology(), FakeConnectivityController())
    job_id = service.start(_connectivity_payload())
    _wait_for_connectivity(service, job_id)

    export = service.export(job_id, "csv")

    assert export["filename"] == f"connectivity-{job_id}.csv"
    assert export["content_type"] == "text/csv"
    lines = export["content"].splitlines()
    assert lines[0] == (
        "source,destination,reachable,packets_transmitted,packets_received,"
        "packet_loss_percent,rtt_min_ms,rtt_avg_ms,rtt_max_ms,error"
    )
    assert "Sat0,Sat1,true,3,3,0.0,1.0,1.5,2.0," in lines
    assert "Sat1,Sat0,false,3,0,100.0,,,,no reply" in lines


def test_connectivity_export_json_for_a_done_job() -> None:
    """Done jobs export the matrix as JSON with node order and results."""
    service = ConnectivityService(_ready_topology(), FakeConnectivityController())
    job_id = service.start(_connectivity_payload())
    _wait_for_connectivity(service, job_id)

    export = service.export(job_id, "json")
    data = json.loads(export["content"])

    assert export["filename"] == f"connectivity-{job_id}.json"
    assert export["content_type"] == "application/json"
    assert data["nodes"] == ["Sat0", "Sat1"]
    assert data["summary"]["pairs"] == 2
    assert data["results"][0]["destination"] == "Sat1"


def test_connectivity_export_rejects_a_running_job() -> None:
    """A running job has no exportable matrix yet."""
    started = threading.Event()
    release = threading.Event()

    class BlockingController(FakeConnectivityController):
        def run_connectivity_matrix(self, topology, names, **kwargs):
            started.set()
            release.wait(timeout=5)
            return _matrix_result()

    service = ConnectivityService(_ready_topology(), BlockingController())
    job_id = service.start(_connectivity_payload())
    try:
        assert started.wait(timeout=2)
        with pytest.raises(APIError) as error:
            service.export(job_id, "csv")
        assert error.value.status_code == 409
        assert "running" in error.value.message.lower()
    finally:
        release.set()
    _wait_for_connectivity(service, job_id)


def test_connectivity_export_rejects_a_failed_job() -> None:
    """A failed job cannot export partial or fabricated results."""
    controller = FakeConnectivityController(error=RuntimeError("matrix exploded"))
    service = ConnectivityService(_ready_topology(), controller)
    job_id = service.start(_connectivity_payload())
    _wait_for_connectivity(service, job_id)

    with pytest.raises(APIError) as error:
        service.export(job_id, "csv")

    assert error.value.status_code == 409
    assert "failed" in error.value.message.lower()


def test_connectivity_rejects_a_fifth_running_job() -> None:
    """At most four running checks hold the queue."""
    started = threading.Event()
    release = threading.Event()

    class BlockingController(FakeConnectivityController):
        def run_connectivity_matrix(self, topology, names, **kwargs):
            started.set()
            release.wait(timeout=5)
            return _matrix_result()

    service = ConnectivityService(_ready_topology(), BlockingController())
    job_ids = [service.start(_connectivity_payload()) for _ in range(4)]
    try:
        assert started.wait(timeout=2)
        with pytest.raises(APIError) as error:
            service.start(_connectivity_payload())
        assert error.value.status_code == 429
        assert len(service.jobs.running()) == 4
    finally:
        release.set()
    for job_id in job_ids:
        _wait_for_connectivity(service, job_id)


def test_connectivity_registry_prunes_expired_terminal_jobs() -> None:
    """Terminal jobs are removed after the one-hour in-memory TTL."""
    now = 0.0
    registry = ConnectivityJobRegistry(
        max_jobs=4,
        ttl_seconds=10,
        clock=lambda: now,
    )
    job = registry.create(
        nodes=["Sat0", "Sat1"],
        ping_count=1,
        max_workers=1,
        flow_timeout_seconds=1.0,
        pair_count=2,
        generation=1,
    )
    assert job.transition(
        "done",
        summary={"pairs": 2, "reachable": 2, "unreachable": 0},
        results=[],
    )
    now = 100.0

    registry.prune()

    assert registry.get(job.job_id) is None


def test_connectivity_terminal_transitions_are_immutable() -> None:
    """Once a job is terminal, a late worker result cannot overwrite it."""
    registry = ConnectivityJobRegistry(max_jobs=1)
    job = registry.create(
        nodes=["Sat0", "Sat1"],
        ping_count=1,
        max_workers=1,
        flow_timeout_seconds=1.0,
        pair_count=2,
        generation=1,
    )

    assert job.transition("done", summary={"pairs": 2}, results=[]) is True
    assert job.transition("error", error="late failure") is False
    assert job.snapshot()["status"] == "done"
    assert job.snapshot()["error"] is None


def test_connectivity_registry_evicts_terminal_jobs_before_capacity() -> None:
    """Finished jobs free their slot instead of blocking new checks."""
    registry = ConnectivityJobRegistry(max_jobs=1)
    first = registry.create(
        nodes=["Sat0", "Sat1"],
        ping_count=1,
        max_workers=1,
        flow_timeout_seconds=1.0,
        pair_count=2,
        generation=1,
    )
    first.transition("done", summary={"pairs": 2}, results=[])

    second = registry.create(
        nodes=["Sat0", "Sat1"],
        ping_count=1,
        max_workers=1,
        flow_timeout_seconds=1.0,
        pair_count=2,
        generation=1,
    )

    assert registry.get(first.job_id) is None
    assert registry.get(second.job_id) is second


# ---------------------------------------------------------------------------
# Experiment runs
# ---------------------------------------------------------------------------

MINIMAL_EXPERIMENT_YAML = """\
name: Service Experiment
duration_s: 5
tick_s: 1
shells:
  - identifier: LEO
    planes: 2
    satellites_per_plane: 2
"""


class FakeExperimentTopology:
    """Minimal topology state used by the live-run guard."""

    def __init__(self, running: bool = False) -> None:
        self.running = running
        self.session = ProjectSession()

    def network_running(self) -> bool:
        return self.running


class FakeExperimentGateway:
    """In-memory experiment gateway with recording and failure hooks."""

    def __init__(
        self,
        name: str = "Test Experiment",
        errors: list[str] | None = None,
        run_error: Exception | None = None,
        validate_error: Exception | None = None,
    ) -> None:
        self.name = name
        self.errors = list(errors or [])
        self.run_error = run_error
        self.validate_error = validate_error
        self.validated: list = []
        self.runs: list = []

    def validate_scenario(self, path):
        self.validated.append(path)
        if self.validate_error is not None:
            raise self.validate_error
        return {
            "name": self.name,
            "shells": 1,
            "ground_stations": 0,
            "traffic": 0,
            "events": 0,
            "connectivity": False,
            "duration_s": 5,
        }

    def run_scenario(self, path, run_dir, mode):
        self.runs.append((path, run_dir, mode))
        if self.run_error is not None:
            raise self.run_error
        return {
            "summary": {"flows": {"count": 0}, "mode": mode},
            "errors": list(self.errors),
        }

    def core_version(self) -> str:
        return "0.3.2-test"


class BlockingExperimentGateway(FakeExperimentGateway):
    """Gateway whose runs block until the test releases them."""

    def __init__(self, wait_for: int = 1) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()
        self._run_lock = threading.Lock()
        self._wait_for = wait_for
        self._started_count = 0

    def run_scenario(self, path, run_dir, mode):
        self.runs.append((path, run_dir, mode))
        with self._run_lock:
            self._started_count += 1
            if self._started_count >= self._wait_for:
                self.started.set()
        assert self.release.wait(timeout=5)
        return {"summary": {"flows": 0, "mode": mode}, "errors": []}


def _experiment_payload(mode: str = "offline") -> ExperimentStartRequest:
    return ExperimentStartRequest(scenario_yaml=MINIMAL_EXPERIMENT_YAML, mode=mode)


def _experiment_service(
    save_root,
    gateway: FakeExperimentGateway,
    *,
    network_running: bool = False,
) -> ExperimentService:
    return ExperimentService(
        Settings("127.0.0.1", 8000, save_root),
        FakeExperimentTopology(running=network_running),
        gateway,
    )


def _wait_for_experiment(
    service: ExperimentService,
    run_id: str,
    timeout: float = 5.0,
) -> dict:
    deadline = time.monotonic() + timeout
    status = None
    while time.monotonic() < deadline:
        status = service.status(run_id)
        if status["status"] != "running":
            return status
        time.sleep(0.01)
    raise AssertionError(f"experiment did not finish: {status}")


@pytest.mark.parametrize("mode", ["dry_run", "offline"])
def test_experiment_start_and_status_done(tmp_path, mode: str) -> None:
    """Dry and offline starts run the gateway and finish in the background."""
    gateway = FakeExperimentGateway()
    service = _experiment_service(tmp_path / mode, gateway)

    run_id = service.start(_experiment_payload(mode))
    status = _wait_for_experiment(service, run_id)

    assert run_id.startswith("exp-")
    assert status["status"] == "done"
    assert status["mode"] == mode
    assert status["name"] == "Test Experiment"
    assert status["summary"]["mode"] == mode
    assert status["finished_at"] is not None
    assert gateway.runs[0][2] == mode
    assert gateway.validated


def test_experiment_list_and_artifact_round_trip(tmp_path) -> None:
    """Completed runs are listed newest first and serve allowlisted artifacts."""
    gateway = FakeExperimentGateway()
    service = _experiment_service(tmp_path, gateway)

    run_id = service.start(_experiment_payload())
    _wait_for_experiment(service, run_id)

    listing = service.list_runs()
    assert listing["ok"] is True
    assert [run["run_id"] for run in listing["runs"]] == [run_id]
    entry = listing["runs"][0]
    assert entry["status"] == "done"
    assert entry["summary"]["mode"] == "offline"
    assert {
        "scenario.yaml",
        "provenance.json",
        "summary.json",
        "errors.json",
    } <= set(entry["artifacts"])
    assert "metrics.jsonl" not in entry["artifacts"]

    artifact = service.artifact(run_id, "summary.json")
    assert artifact["filename"] == "summary.json"
    assert artifact["content_type"] == "application/json"
    assert json.loads(artifact["content"])["mode"] == "offline"
    scenario = service.artifact(run_id, "scenario.yaml")
    assert scenario["content"] == MINIMAL_EXPERIMENT_YAML
    assert scenario["content_type"] == "text/yaml"
    provenance = service.artifact(run_id, "provenance.json")
    assert provenance["content_type"] == "application/json"


def test_experiment_invalid_scenario_is_422_and_cleans_up(tmp_path) -> None:
    """Validation failures return 422 and remove the reserved run directory."""
    gateway = FakeExperimentGateway(validate_error=ValueError("missing shells"))
    service = _experiment_service(tmp_path, gateway)

    with pytest.raises(APIError) as error:
        service.start(_experiment_payload())

    assert error.value.status_code == 422
    assert "missing shells" in error.value.message
    assert (tmp_path / ".satgonetem" / "experiments").is_dir()
    assert list((tmp_path / ".satgonetem" / "experiments").iterdir()) == []


def test_experiment_live_guard_requires_stopped_containers(tmp_path) -> None:
    """Live runs are rejected while GoNetEm containers are up."""
    gateway = FakeExperimentGateway()
    service = _experiment_service(tmp_path, gateway, network_running=True)

    with pytest.raises(APIError) as error:
        service.start(_experiment_payload("live"))

    assert error.value.status_code == 409
    assert "container" in error.value.message.lower()
    assert gateway.validated == []
    assert gateway.runs == []


def test_experiment_live_single_flight(tmp_path) -> None:
    """Only one live run may be active at a time."""
    gateway = BlockingExperimentGateway()
    service = _experiment_service(tmp_path, gateway)

    run_id = service.start(_experiment_payload("live"))
    assert gateway.started.wait(timeout=5)
    try:
        with pytest.raises(APIError) as error:
            service.start(_experiment_payload("live"))
        assert error.value.status_code == 409
    finally:
        gateway.release.set()

    assert _wait_for_experiment(service, run_id)["status"] == "done"


def test_experiment_capacity_limit_is_429(tmp_path) -> None:
    """At most two runs execute at once, and finished runs free their slot."""
    gateway = BlockingExperimentGateway(wait_for=2)
    service = _experiment_service(tmp_path, gateway)

    first = service.start(_experiment_payload("offline"))
    second = service.start(_experiment_payload("dry_run"))
    assert gateway.started.wait(timeout=5)
    try:
        with pytest.raises(APIError) as error:
            service.start(_experiment_payload("offline"))
        assert error.value.status_code == 429
    finally:
        gateway.release.set()

    assert _wait_for_experiment(service, first)["status"] == "done"
    assert _wait_for_experiment(service, second)["status"] == "done"

    third = service.start(_experiment_payload("dry_run"))
    assert _wait_for_experiment(service, third)["status"] == "done"


def test_experiment_artifact_traversal_is_404(tmp_path) -> None:
    """Artifact names and run ids cannot escape their directories."""
    run_id = "exp-unknown"
    gateway = FakeExperimentGateway()
    service = _experiment_service(tmp_path, gateway)
    real_run = service.start(_experiment_payload())
    _wait_for_experiment(service, real_run)

    with pytest.raises(APIError) as error:
        service.artifact(real_run, "../provenance.json")
    assert error.value.status_code == 404

    with pytest.raises(APIError) as error:
        service.artifact(real_run, "scenario.yaml/../../provenance.json")
    assert error.value.status_code == 404

    with pytest.raises(APIError) as error:
        service.artifact("..", "summary.json")
    assert error.value.status_code == 404

    with pytest.raises(APIError) as error:
        service.status("missing")
    assert error.value.status_code == 404

    with pytest.raises(APIError) as error:
        service.artifact(run_id, "summary.json")
    assert error.value.status_code == 404


def test_experiment_artifact_rejects_symlink_escape(tmp_path) -> None:
    """An in-run symlink pointing outside the run directory is not served."""
    gateway = FakeExperimentGateway()
    service = _experiment_service(tmp_path, gateway)
    run_id = service.start(_experiment_payload())
    _wait_for_experiment(service, run_id)

    run_dir = next((tmp_path / ".satgonetem" / "experiments").iterdir())
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    (run_dir / "connectivity.json").symlink_to(outside)

    with pytest.raises(APIError) as error:
        service.artifact(run_id, "connectivity.json")
    assert error.value.status_code == 404
    assert "connectivity.json" not in service.list_runs()["runs"][0]["artifacts"]


def test_experiment_provenance_and_artifact_writes(tmp_path) -> None:
    """Provenance records versions, hashes, and no absolute paths."""
    gateway = FakeExperimentGateway()
    service = _experiment_service(tmp_path, gateway)

    run_id = service.start(_experiment_payload())
    _wait_for_experiment(service, run_id)

    run_dir = next((tmp_path / ".satgonetem" / "experiments").iterdir())
    provenance_text = (run_dir / "provenance.json").read_text(encoding="utf-8")
    provenance = json.loads(provenance_text)
    assert provenance["run_id"] == run_id
    assert provenance["name"] == "Test Experiment"
    assert provenance["mode"] == "offline"
    assert provenance["status"] == "done"
    assert provenance["core_version"] == "0.3.2-test"
    assert provenance["gui_version"]
    assert provenance["scenario_filename"] == "scenario.yaml"
    assert (
        provenance["scenario_sha256"]
        == hashlib.sha256(MINIMAL_EXPERIMENT_YAML.encode("utf-8")).hexdigest()
    )
    assert provenance["started_at"]
    assert provenance["finished_at"]
    assert str(tmp_path) not in provenance_text
    assert (run_dir / "scenario.yaml").read_text(encoding="utf-8") == (MINIMAL_EXPERIMENT_YAML)
    assert (run_dir / "summary.json").is_file()
    assert (run_dir / "errors.json").is_file()


def test_experiment_worker_failure_records_error_and_keeps_artifacts(tmp_path) -> None:
    """A failed run stays on disk with its status, message, and partial files."""
    gateway = FakeExperimentGateway(run_error=RuntimeError("simulation exploded"))
    service = _experiment_service(tmp_path, gateway)

    run_id = service.start(_experiment_payload())
    status = _wait_for_experiment(service, run_id)

    assert status["status"] == "error"
    assert status["summary"] is None
    assert "simulation exploded" in status["errors"][0]
    run_dir = next((tmp_path / ".satgonetem" / "experiments").iterdir())
    provenance = json.loads((run_dir / "provenance.json").read_text(encoding="utf-8"))
    assert provenance["status"] == "error"
    assert json.loads((run_dir / "errors.json").read_text(encoding="utf-8"))
    assert (run_dir / "scenario.yaml").is_file()


def test_experiment_list_skips_symlinked_and_malformed_runs(tmp_path) -> None:
    """The catalog scanner ignores escapes and incomplete directories."""
    gateway = FakeExperimentGateway()
    service = _experiment_service(tmp_path, gateway)
    run_id = service.start(_experiment_payload())
    _wait_for_experiment(service, run_id)

    run_root = tmp_path / ".satgonetem" / "experiments"
    malformed = run_root / "exp-malformed"
    malformed.mkdir()
    (malformed / "provenance.json").write_text("not-json", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (run_root / "exp-outside").symlink_to(outside)

    listing = service.list_runs()

    assert [run["run_id"] for run in listing["runs"]] == [run_id]


def test_experiment_live_holds_the_network_operation_until_done(tmp_path) -> None:
    """A live run blocks project/network mutations for its whole duration."""
    gateway = BlockingExperimentGateway()
    service = _experiment_service(tmp_path, gateway)

    run_id = service.start(_experiment_payload("live"))
    assert service.topology.session.network_operation is True
    try:
        assert (
            service.topology.session.begin(
                "Blocked",
                operation="create",
            )
            is False
        )
    finally:
        gateway.release.set()

    assert _wait_for_experiment(service, run_id)["status"] == "done"
    assert service.topology.session.network_operation is False
