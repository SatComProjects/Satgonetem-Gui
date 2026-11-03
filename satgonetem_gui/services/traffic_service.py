"""Traffic job orchestration and in-memory job registry."""

import logging
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from ..errors import APIError
from ..schemas import Hping3Request, Iperf3Request, PingRequest
from .ports import TrafficGateway
from .topology_service import TopologyService

logger = logging.getLogger(__name__)


@dataclass
class TrafficJob:
    """One in-flight or completed traffic flow."""

    job_id: str
    kind: str
    flow: Any
    src: str
    dst: str
    status: str = "running"
    results: dict[str, Any] | None = None
    error: str | None = None


@dataclass
class JobRegistry:
    """Thread-safe job storage with stable IDs."""

    _jobs: dict[str, TrafficJob] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def create(self, kind: str, flow: Any, src: str, dst: str) -> TrafficJob:
        """Create and store a new running job."""
        job = TrafficJob(
            job_id=f"j{uuid.uuid4().hex}",
            kind=kind,
            flow=flow,
            src=src,
            dst=dst,
        )
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> TrafficJob | None:
        """Return a job by ID."""
        with self._lock:
            return self._jobs.get(job_id)


class TrafficService:
    """Start and poll traffic flows for the loaded topology."""

    def __init__(
        self,
        topology: TopologyService,
        gateway: TrafficGateway,
        jobs: JobRegistry | None = None,
    ) -> None:
        self.topology = topology
        self.gateway = gateway
        self.jobs = jobs or JobRegistry()

    def nodes(self) -> list[dict[str, str]]:
        """Return valid traffic endpoints."""
        return self.topology.traffic_nodes()

    def _start(
        self,
        kind: str,
        src_name: str,
        dst_name: str,
        starter: Callable[[Any, Any], Any],
    ) -> str:
        self.topology.require_topology()
        if not self.topology.gonetem_is_on():
            raise APIError(409, "GoNetEm is not running.")

        source = self.topology.find_node(src_name)
        destination = self.topology.find_node(dst_name)
        if source is None or destination is None:
            raise APIError(404, f"Node not found: {src_name} or {dst_name}")

        try:
            flow = starter(source, destination)
        except Exception as exc:
            logger.exception("Failed to start %s flow.", kind)
            raise APIError(500, f"Failed to start {kind} flow.") from exc

        job = self.jobs.create(kind, flow, src_name, dst_name)
        return job.job_id

    def start_iperf3(self, request: Iperf3Request) -> str:
        """Start an iperf3 job."""
        return self._start(
            "iperf3",
            request.src,
            request.dst,
            lambda source, destination: self.gateway.start_iperf3(
                source, destination, request
            ),
        )

    def start_ping(self, request: PingRequest) -> str:
        """Start a ping job."""
        return self._start(
            "ping",
            request.src,
            request.dst,
            lambda source, destination: self.gateway.start_ping(
                source, destination, request
            ),
        )

    def start_hping3(self, request: Hping3Request) -> str:
        """Start an hping3 job."""
        return self._start(
            "hping3",
            request.src,
            request.dst,
            lambda source, destination: self.gateway.start_hping3(
                source, destination, request
            ),
        )

    def status(self, job_id: str) -> dict:
        """Poll one job and update its stored state."""
        job = self.jobs.get(job_id)
        if job is None:
            raise APIError(404, "Job not found.")

        try:
            poll = self.gateway.poll(job.flow)
        except Exception as exc:
            logger.exception("Error polling traffic job status.")
            raise APIError(500, "Error polling traffic job status.") from exc

        job.status = poll.status
        if poll.results is not None:
            job.results = poll.results
        if poll.error is not None:
            job.error = poll.error

        response: dict[str, Any] = {"status": poll.status}
        if poll.results is not None:
            response["results"] = poll.results
        if poll.error is not None:
            response["error"] = poll.error
        return response

    def cancel(self, job_id: str) -> None:
        """Mark a job cancelled.

        Real flow termination is implemented in Phase 4.
        """
        job = self.jobs.get(job_id)
        if job is None:
            raise APIError(404, "Job not found.")
        job.status = "cancelled"
