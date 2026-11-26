"""Unit tests for traffic jobs, strategies, and the job registry."""

import threading

import pytest

from satgonetem_gui.errors import APIError
from satgonetem_gui.schemas import Iperf3Request, PingRequest
from satgonetem_gui.services.ports import TrafficPoll
from satgonetem_gui.services.topology_service import TopologyService
from satgonetem_gui.services.traffic_service import (
    JobCapacityError,
    JobRegistry,
    TrafficJob,
    TrafficService,
)
from satgonetem_gui.state import ProjectSession
from tests.service_fakes import FakeReader, _loaded_session, _ready_topology


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
    assert error.value.message == "Traffic job limit reached."
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
