"""Unit tests for service orchestration with fake gateways."""

import asyncio

import pytest

from satgonetem_gui.errors import APIError
from satgonetem_gui.schemas import Iperf3Request, PingRequest
from satgonetem_gui.services.ports import TrafficPoll
from satgonetem_gui.services.routing_service import RoutingService
from satgonetem_gui.services.topology_service import TopologyService
from satgonetem_gui.services.traffic_service import (
    JobCapacityError,
    JobRegistry,
    TrafficJob,
    TrafficService,
)
from satgonetem_gui.state import ProjectSession


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

    def routing_status(self, topology):
        return {
            "ok": True,
            "gonetem_is_on": False,
            "addressing_applied": False,
            "routing_initiated": False,
            "routing_method": "static",
        }

    def apply_routing(self, topology, method):
        raise AssertionError("should not run while GoNetEm is stopped")


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


def test_traffic_rejects_unknown_kind() -> None:
    """Only registered flow strategies can be started."""
    topology = TopologyService(_loaded_session(), FakeReader(gonetem=True))
    service = TrafficService(topology, FakeTraffic())

    with pytest.raises(APIError) as error:
        service.start("unknown", Iperf3Request(src="Sat0", dst="Sat0"))

    assert error.value.status_code == 400


def test_traffic_start_and_status() -> None:
    """A started job is polled through the one status path."""
    topology = TopologyService(_loaded_session(), FakeReader(gonetem=True))
    gateway = FakeTraffic()
    service = TrafficService(topology, gateway)

    job_id = service.start("ping", PingRequest(src="Sat0", dst="Sat0"))

    assert job_id.startswith("j")
    assert service.status(job_id) == {"status": "done", "results": {"ok": True}}
    assert gateway.poll_calls == 1


def test_traffic_cancel_stops_flow_and_stays_cancelled() -> None:
    """Cancel calls stop, marks the job terminal, and avoids future polling."""
    topology = TopologyService(_loaded_session(), FakeReader(gonetem=True))
    gateway = FakeTraffic(poll_status="running")
    service = TrafficService(topology, gateway)
    job_id = service.start("ping", PingRequest(src="Sat0", dst="Sat0"))
    job = service.jobs.get(job_id)

    service.cancel(job_id)

    assert job is not None
    assert job.status == "cancelled"
    assert gateway.stopped == [job.flow]
    assert service.status(job_id) == {"status": "cancelled"}
    assert gateway.poll_calls == 0


def test_traffic_cancel_failure_keeps_job_running() -> None:
    """A failed stop is reported and does not fake a cancellation."""
    topology = TopologyService(_loaded_session(), FakeReader(gonetem=True))
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
    topology = TopologyService(_loaded_session(), FakeReader(gonetem=True))
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
    job.updated_at = 0.0
    now = 100.0

    registry.prune()

    assert registry.get(job.job_id) is None


def test_capacity_rejection_stops_the_unregistered_flow() -> None:
    """A flow that cannot be registered is stopped instead of leaking."""
    topology = TopologyService(_loaded_session(), FakeReader(gonetem=True))
    gateway = FakeTraffic()
    jobs = JobRegistry(max_jobs=1)
    jobs.create("ping", object(), "a", "b")
    service = TrafficService(topology, gateway, jobs)

    with pytest.raises(APIError) as error:
        service.start("ping", PingRequest(src="Sat0", dst="Sat0"))

    assert error.value.status_code == 429
    assert len(gateway.stopped) == 1


def test_strategy_registry_covers_all_tools() -> None:
    """The registry exposes exactly the typed traffic strategies."""
    from satgonetem_gui.schemas import Hping3Request

    topology = TopologyService(_loaded_session(), FakeReader(gonetem=True))
    service = TrafficService(topology, FakeTraffic())

    assert set(service.strategies) == {"iperf3", "ping", "hping3"}
    assert service.strategies["iperf3"].request_type is Iperf3Request
    assert service.strategies["ping"].request_type is PingRequest
    assert service.strategies["hping3"].request_type is Hping3Request
