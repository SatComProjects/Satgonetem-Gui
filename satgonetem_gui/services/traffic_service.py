"""Traffic job orchestration and bounded in-memory job registry."""

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from ..errors import APIError
from ..schemas import Hping3Request, Iperf3Request, PingRequest
from .ports import TrafficGateway
from .topology_service import TopologyService

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = frozenset({"done", "error", "cancelled"})


class JobCapacityError(RuntimeError):
    """Raised when the job registry cannot evict enough terminal jobs."""


@dataclass(frozen=True)
class TrafficStrategy:
    """One supported traffic tool and its typed request."""

    kind: str
    request_type: type
    start: Callable[[Any, Any, Any], Any]


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
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    clock: Callable[[], float] = field(default=time.time, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    @property
    def lock(self) -> threading.RLock:
        """Return the per-job synchronization lock."""
        return self._lock

    @property
    def terminal(self) -> bool:
        """Return True once the job reached a terminal state."""
        with self._lock:
            return self.status in TERMINAL_STATUSES

    def transition(
        self,
        status: str,
        *,
        results: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> bool:
        """Move a running job to a terminal state; terminal jobs are immutable."""
        with self._lock:
            if self.status in TERMINAL_STATUSES:
                return False
            self.status = status
            if results is not None:
                self.results = results
            if error is not None:
                self.error = error
            self.updated_at = self.clock()
            return True

    def snapshot(self) -> dict[str, Any]:
        """Return a response-shaped snapshot without exposing the flow."""
        with self._lock:
            response: dict[str, Any] = {"status": self.status}
            if self.results is not None:
                response["results"] = self.results
            if self.error is not None:
                response["error"] = self.error
            return response


@dataclass
class JobRegistry:
    """Thread-safe, bounded job storage with TTL cleanup."""

    max_jobs: int = 100
    ttl_seconds: float = 3600.0
    clock: Callable[[], float] = time.time
    _jobs: dict[str, TrafficJob] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        if self.max_jobs < 1:
            raise ValueError("max_jobs must be at least 1")
        if self.ttl_seconds < 0:
            raise ValueError("ttl_seconds must be non-negative")

    def __len__(self) -> int:
        with self._lock:
            return len(self._jobs)

    def create(self, kind: str, flow: Any, src: str, dst: str) -> TrafficJob:
        """Create a running job, pruning expired/finished entries if needed."""
        with self._lock:
            self._prune_locked(self.clock())
            if len(self._jobs) >= self.max_jobs:
                self._evict_terminal_locked()
            if len(self._jobs) >= self.max_jobs:
                raise JobCapacityError("Traffic job limit reached.")
            now = self.clock()
            job = TrafficJob(
                job_id=f"j{uuid.uuid4().hex}",
                kind=kind,
                flow=flow,
                src=src,
                dst=dst,
                created_at=now,
                updated_at=now,
                clock=self.clock,
            )
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> TrafficJob | None:
        """Return a job by ID."""
        with self._lock:
            return self._jobs.get(job_id)

    def running(self) -> list[TrafficJob]:
        """Return a snapshot of jobs that have not reached a terminal state."""
        with self._lock:
            return [job for job in self._jobs.values() if not job.terminal]

    def prune(self) -> None:
        """Remove terminal jobs older than the TTL."""
        with self._lock:
            self._prune_locked(self.clock())

    def _prune_locked(self, now: float) -> None:
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.terminal and now - job.updated_at >= self.ttl_seconds
        ]
        for job_id in expired:
            del self._jobs[job_id]

    def _evict_terminal_locked(self) -> None:
        terminal = sorted(
            (job for job in self._jobs.values() if job.terminal),
            key=lambda job: job.updated_at,
        )
        while len(self._jobs) >= self.max_jobs and terminal:
            job = terminal.pop(0)
            self._jobs.pop(job.job_id, None)


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
        self.jobs = jobs if jobs is not None else JobRegistry()
        self.strategies = {
            "iperf3": TrafficStrategy("iperf3", Iperf3Request, gateway.start_iperf3),
            "ping": TrafficStrategy("ping", PingRequest, gateway.start_ping),
            "hping3": TrafficStrategy("hping3", Hping3Request, gateway.start_hping3),
        }

    def nodes(self) -> list[dict[str, str]]:
        """Return valid traffic endpoints."""
        return self.topology.traffic_nodes()

    def start(self, kind: str, request: Any) -> str:
        """Start a job for a registered traffic kind."""
        strategy = self.strategies.get(kind)
        if strategy is None:
            raise APIError(400, f"Unsupported traffic kind: {kind}.")
        if not isinstance(request, strategy.request_type):
            raise APIError(422, f"Invalid request for {kind}.")

        self.topology.require_topology()
        if not self.topology.gonetem_is_on():
            raise APIError(409, "GoNetEm is not running.")

        source = self.topology.find_node(request.src)
        destination = self.topology.find_node(request.dst)
        if source is None or destination is None:
            raise APIError(404, f"Node not found: {request.src} or {request.dst}")

        try:
            flow = strategy.start(source, destination, request)
        except Exception as exc:
            logger.exception("Failed to start %s flow.", kind)
            raise APIError(500, f"Failed to start {kind} flow.") from exc

        try:
            job = self._create_job(kind, flow, request)
        except JobCapacityError as exc:
            try:
                self.gateway.stop(flow)
            except Exception:
                logger.exception("Failed to stop a rejected traffic flow.")
            raise APIError(429, str(exc)) from exc
        return job.job_id

    def _create_job(self, kind: str, flow: Any, request: Any) -> TrafficJob:
        """Create a job, reclaiming finished jobs once when the registry is full."""
        try:
            return self.jobs.create(kind, flow, request.src, request.dst)
        except JobCapacityError:
            self._poll_running_jobs()
            return self.jobs.create(kind, flow, request.src, request.dst)

    def _poll_running_jobs(self) -> None:
        """Poll every running job once so unpolled finished jobs become evictable."""
        for job in self.jobs.running():
            try:
                self.status(job.job_id)
            except APIError:
                logger.debug("Lazy poll failed for traffic job %s.", job.job_id)

    def status(self, job_id: str) -> dict:
        """Poll one job and apply one terminal-state transition."""
        self.jobs.prune()
        job = self.jobs.get(job_id)
        if job is None:
            raise APIError(404, "Job not found.")

        with job.lock:
            if job.status in TERMINAL_STATUSES:
                return job.snapshot()
            try:
                poll = self.gateway.poll(job.kind, job.flow)
            except Exception as exc:
                logger.exception("Error polling traffic job status.")
                raise APIError(500, "Error polling traffic job status.") from exc
            if poll.status == "running":
                return {"status": "running"}
            if poll.status in TERMINAL_STATUSES:
                job.transition(
                    poll.status,
                    results=poll.results,
                    error=poll.error,
                )
            else:
                job.transition("error", error="Unknown flow state.")
            return job.snapshot()

    def cancel(self, job_id: str) -> None:
        """Poll once, then stop a still-running flow and mark it cancelled."""
        self.jobs.prune()
        job = self.jobs.get(job_id)
        if job is None:
            raise APIError(404, "Job not found.")

        with job.lock:
            if job.status == "cancelled":
                return
            if job.status in TERMINAL_STATUSES:
                raise APIError(409, "Job is already finished.")
            try:
                poll = self.gateway.poll(job.kind, job.flow)
            except Exception as exc:
                logger.exception("Error polling traffic job status before cancel.")
                raise APIError(
                    500,
                    "Could not verify the traffic job state; retry cancel.",
                ) from exc
            if poll.status != "running":
                if poll.status in TERMINAL_STATUSES:
                    job.transition(
                        poll.status,
                        results=poll.results,
                        error=poll.error,
                    )
                else:
                    job.transition("error", error="Unknown flow state.")
                raise APIError(409, "Job is already finished.")
            try:
                self.gateway.stop(job.flow)
            except Exception as exc:
                logger.exception("Failed to stop traffic flow.")
                raise APIError(500, "Failed to stop traffic flow.") from exc
            job.transition("cancelled")
