"""Service tests for the bounded throughput matrix."""

import threading
import time
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from satgonetem_gui.errors import APIError
from satgonetem_gui.schemas import TrafficMatrixRequest
from satgonetem_gui.services.traffic_matrix_service import TrafficMatrixService


class FakeMatrixTopology:
    def __init__(self) -> None:
        self.gonetem = True
        self.addressing = True
        self.generation = 1

    @property
    def addressing_applied(self) -> bool:
        return self.addressing

    def context(self):
        return SimpleNamespace(), self.generation

    def gonetem_is_on(self) -> bool:
        return self.gonetem


class FakeMatrixTraffic:
    def __init__(self, error_pairs=None, block=None) -> None:
        self.error_pairs = set(error_pairs or [])
        self.block = block
        self.calls = []
        self.jobs = {}

    def nodes(self):
        return [{"name": f"Gnd{index}"} for index in range(12)]

    def start(self, kind, request):
        job_id = f"j{len(self.calls)}"
        self.calls.append((kind, request.src, request.dst))
        self.jobs[job_id] = (request.src, request.dst)
        return job_id

    def status(self, job_id):
        if self.block is not None and not self.block.is_set():
            return {"status": "running"}
        source, destination = self.jobs[job_id]
        if (source, destination) in self.error_pairs:
            return {"status": "error", "error": "pair failed"}
        return {"status": "done", "results": {"avg_throughput_mbps": 10.0}}


def _service(traffic=None):
    topology = FakeMatrixTopology()
    traffic = traffic or FakeMatrixTraffic()
    service = TrafficMatrixService(
        topology,
        traffic,
        poll_interval=0.001,
    )
    return service, topology, traffic


def _wait(service, job_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = service.status(job_id)
        if status["status"] != "running":
            return status
        time.sleep(0.005)
    raise AssertionError(status)


def test_matrix_runs_ordered_pairs_and_builds_matrix() -> None:
    service, _topology, traffic = _service()

    job_id = service.start(TrafficMatrixRequest(nodes=["Gnd0", "Gnd1"], duration_s=1))
    status = _wait(service, job_id)

    assert status["status"] == "done"
    assert status["nodes"] == ["Gnd0", "Gnd1"]
    assert status["pairs_total"] == 2
    assert status["pairs_completed"] == 2
    assert status["matrix"] == [[None, 10.0], [10.0, None]]
    assert [(call[1], call[2]) for call in traffic.calls] == [
        ("Gnd0", "Gnd1"),
        ("Gnd1", "Gnd0"),
    ]


def test_pair_errors_are_retained_without_failing_the_job() -> None:
    service, _topology, _traffic = _service(FakeMatrixTraffic(error_pairs={("Gnd0", "Gnd1")}))

    job_id = service.start(TrafficMatrixRequest(nodes=["Gnd0", "Gnd1"], duration_s=1))
    status = _wait(service, job_id)

    results = {(item["src"], item["dst"]): item for item in status["results"]}
    assert status["status"] == "done"
    assert results[("Gnd0", "Gnd1")]["status"] == "error"
    assert results[("Gnd0", "Gnd1")]["error"] == "pair failed"
    assert results[("Gnd1", "Gnd0")]["status"] == "done"


def test_preconditions_and_node_caps() -> None:
    service, topology, _traffic = _service()
    request = TrafficMatrixRequest(nodes=["Gnd0", "Gnd1"])

    topology.gonetem = False
    with pytest.raises(APIError) as error:
        service.start(request)
    assert error.value.status_code == 409

    topology.gonetem = True
    topology.addressing = False
    with pytest.raises(APIError) as error:
        service.start(request)
    assert error.value.status_code == 409

    topology.addressing = True
    with pytest.raises(APIError) as error:
        service.start(TrafficMatrixRequest(nodes=["Gnd0"]))
    assert error.value.status_code == 422

    with pytest.raises(ValidationError):
        TrafficMatrixRequest(nodes=[f"Gnd{index}" for index in range(13)])

    with pytest.raises(APIError) as error:
        service.start(TrafficMatrixRequest(nodes=["Gnd0", "Gnd0"]))
    assert error.value.status_code == 422
    assert "unique" in error.value.message

    with pytest.raises(APIError) as error:
        service.start(TrafficMatrixRequest(nodes=["Gnd0", "Missing"]))
    assert error.value.status_code == 422
    assert "Unknown" in error.value.message


def test_capacity_and_unknown_job() -> None:
    block = threading.Event()
    service, _topology, _traffic = _service(FakeMatrixTraffic(block=block))

    first = service.start(TrafficMatrixRequest(nodes=["Gnd0", "Gnd1"], timeout_s=5))
    second = service.start(TrafficMatrixRequest(nodes=["Gnd0", "Gnd1"], timeout_s=5))
    try:
        with pytest.raises(APIError) as error:
            service.start(TrafficMatrixRequest(nodes=["Gnd0", "Gnd1"], timeout_s=5))
        assert error.value.status_code == 429
    finally:
        block.set()
    _wait(service, first)
    _wait(service, second)

    with pytest.raises(APIError) as error:
        service.status("missing")
    assert error.value.status_code == 404


def test_export_csv_and_json() -> None:
    service, _topology, _traffic = _service()
    job_id = service.start(TrafficMatrixRequest(nodes=["Gnd0", "Gnd1"], duration_s=1))
    _wait(service, job_id)

    csv_envelope = service.export(job_id, "csv")
    json_envelope = service.export(job_id, "json")

    assert csv_envelope["filename"].endswith(".csv")
    assert "src,dst,throughput_mbps,status,error" in csv_envelope["content"]
    assert "Gnd0,Gnd1,10.0,done" in csv_envelope["content"]
    assert json_envelope["filename"].endswith(".json")
    assert '"Gnd0"' in json_envelope["content"]
