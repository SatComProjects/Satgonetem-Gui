"""Unit tests for connectivity matrices, job exports, and registry limits."""

import json
import threading
import time

import pytest

from satgonetem_gui.errors import APIError
from satgonetem_gui.schemas import ConnectivityStartRequest
from satgonetem_gui.services import connectivity_service
from satgonetem_gui.services.connectivity_service import (
    ConnectivityJob,
    ConnectivityService,
)
from satgonetem_gui.services.job_registry import BoundedJobRegistry
from satgonetem_gui.services.topology_service import TopologyService
from satgonetem_gui.state import ProjectSession
from tests.service_fakes import FakeReader, _loaded_session, _ready_topology


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


def _connectivity_job(
    job_id: str = "c1",
    clock=time.time,
) -> ConnectivityJob:
    """Build one connectivity job record for registry-level tests."""
    return ConnectivityJob(
        job_id=job_id,
        nodes=["Sat0", "Sat1"],
        ping_count=1,
        max_workers=1,
        flow_timeout_seconds=1.0,
        pair_count=2,
        generation=1,
        clock=clock,
    )


def test_connectivity_jobs_share_the_registry_clock() -> None:
    """TTL pruning and job timestamps use the same injectable clock."""
    registry = BoundedJobRegistry[ConnectivityJob](
        max_jobs=4,
        max_active=4,
        clock=lambda: 42.0,
    )
    service = ConnectivityService(
        _ready_topology(),
        FakeConnectivityController(),
        registry,
    )

    job_id = service.start(_connectivity_payload())
    _wait_for_connectivity(service, job_id)
    job = registry.get(job_id)

    assert job is not None
    assert job.created_at == 42.0
    assert job.updated_at == 42.0
    assert job.clock() == 42.0


def test_connectivity_registry_prunes_expired_terminal_jobs() -> None:
    """Terminal jobs are removed after the one-hour in-memory TTL."""
    now = 0.0
    registry = BoundedJobRegistry[ConnectivityJob](
        max_jobs=4,
        ttl_seconds=10,
        clock=lambda: now,
    )
    job = _connectivity_job(clock=lambda: now)
    registry.create(job)
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
    registry = BoundedJobRegistry[ConnectivityJob](max_jobs=1)
    job = _connectivity_job()
    registry.create(job)

    assert job.transition("done", summary={"pairs": 2}, results=[]) is True
    assert job.transition("error", error="late failure") is False
    assert job.snapshot()["status"] == "done"
    assert job.snapshot()["error"] is None


def test_connectivity_registry_evicts_terminal_jobs_before_capacity() -> None:
    """Finished jobs free their slot instead of blocking new checks."""
    registry = BoundedJobRegistry[ConnectivityJob](max_jobs=1)
    first = _connectivity_job("first")
    registry.create(first)
    first.transition("done", summary={"pairs": 2}, results=[])

    second = _connectivity_job("second")
    registry.create(second)

    assert registry.get(first.job_id) is None
    assert registry.get(second.job_id) is second
