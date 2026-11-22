"""Full-mesh connectivity job orchestration and bounded in-memory registry."""

import csv
import io
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from ..errors import APIError
from ..schemas import ConnectivityStartRequest
from .ports import ConnectivityController
from .topology_service import TopologyService

logger = logging.getLogger(__name__)

MAX_NODES = 32
MAX_PAIRS = 2000
MAX_JOBS = 4
TERMINAL_TTL_SECONDS = 3600.0

CSV_HEADER = [
    "source",
    "destination",
    "reachable",
    "packets_transmitted",
    "packets_received",
    "packet_loss_percent",
    "rtt_min_ms",
    "rtt_avg_ms",
    "rtt_max_ms",
    "error",
]


def _utc_timestamp() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _deduplicate(names: list[str]) -> list[str]:
    """Drop duplicate names while preserving request order."""
    seen: set[str] = set()
    ordered: list[str] = []
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    return ordered


class ConnectivityJobCapacityError(RuntimeError):
    """Raised when every connectivity job slot is held by a running check."""


@dataclass
class ConnectivityJob:
    """One running or finished full-mesh connectivity check."""

    job_id: str
    nodes: list[str]
    ping_count: int
    max_workers: int
    flow_timeout_seconds: float
    pair_count: int
    generation: int
    status: str = "running"
    summary: dict[str, Any] | None = None
    results: list[dict[str, Any]] | None = None
    error: str | None = None
    started_at: str = field(default_factory=_utc_timestamp)
    finished_at: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    clock: Callable[[], float] = field(default=time.time, repr=False)
    _started_monotonic: float = field(default_factory=time.monotonic, repr=False)
    _finished_monotonic: float | None = field(default=None, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _terminal: threading.Event = field(default_factory=threading.Event, repr=False, compare=False)

    @property
    def terminal(self) -> bool:
        """Return True once the job reached a terminal state without blocking."""
        return self._terminal.is_set()

    def transition(
        self,
        status: str,
        *,
        summary: dict[str, Any] | None = None,
        results: list[dict[str, Any]] | None = None,
        error: str | None = None,
    ) -> bool:
        """Move a running job to a terminal state; terminal jobs are immutable."""
        with self._lock:
            if self._terminal.is_set():
                return False
            self.status = status
            if summary is not None:
                self.summary = summary
            if results is not None:
                self.results = results
            if error is not None:
                self.error = error
            self.finished_at = _utc_timestamp()
            self._finished_monotonic = time.monotonic()
            self.updated_at = self.clock()
            self._terminal.set()
            return True

    def snapshot(self) -> dict[str, Any]:
        """Return the response-shaped job state without exposing locks."""
        with self._lock:
            finished = self._finished_monotonic
            if finished is None:
                finished = time.monotonic()
            elapsed_ms = max(
                0,
                int((finished - self._started_monotonic) * 1000),
            )
            return {
                "job_id": self.job_id,
                "status": self.status,
                "nodes": list(self.nodes),
                "pair_count": self.pair_count,
                "summary": self.summary,
                "results": list(self.results or []),
                "error": self.error,
                "started_at": self.started_at,
                "finished_at": self.finished_at,
                "elapsed_ms": elapsed_ms,
            }


@dataclass
class ConnectivityJobRegistry:
    """Thread-safe, bounded connectivity job storage with TTL cleanup."""

    max_jobs: int = MAX_JOBS
    ttl_seconds: float = TERMINAL_TTL_SECONDS
    clock: Callable[[], float] = time.time
    _jobs: dict[str, ConnectivityJob] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        if self.max_jobs < 1:
            raise ValueError("max_jobs must be at least 1")
        if self.ttl_seconds < 0:
            raise ValueError("ttl_seconds must be non-negative")

    def __len__(self) -> int:
        with self._lock:
            return len(self._jobs)

    def create(
        self,
        *,
        nodes: list[str],
        ping_count: int,
        max_workers: int,
        flow_timeout_seconds: float,
        pair_count: int,
        generation: int,
    ) -> ConnectivityJob:
        """Create a running job, retaining capacity for running checks."""
        with self._lock:
            now = self.clock()
            self._prune_locked(now)
            running = sum(1 for job in self._jobs.values() if not job.terminal)
            if running >= self.max_jobs:
                raise ConnectivityJobCapacityError(
                    "Connectivity check limit reached. Wait for a running check to finish."
                )
            if len(self._jobs) >= self.max_jobs:
                self._evict_terminal_locked()
            if len(self._jobs) >= self.max_jobs:
                raise ConnectivityJobCapacityError(
                    "Connectivity check limit reached. Wait for a running check to finish."
                )
            job = ConnectivityJob(
                job_id=f"c{uuid.uuid4().hex}",
                nodes=list(nodes),
                ping_count=ping_count,
                max_workers=max_workers,
                flow_timeout_seconds=flow_timeout_seconds,
                pair_count=pair_count,
                generation=generation,
                created_at=now,
                updated_at=now,
                clock=self.clock,
            )
            self._jobs[job.job_id] = job
            return job

    def get(self, job_id: str) -> ConnectivityJob | None:
        """Return a job by ID."""
        with self._lock:
            return self._jobs.get(job_id)

    def running(self) -> list[ConnectivityJob]:
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


class ConnectivityService:
    """Run full-mesh connectivity checks in the background."""

    def __init__(
        self,
        topology: TopologyService,
        controller: ConnectivityController,
        jobs: ConnectivityJobRegistry | None = None,
    ) -> None:
        self.topology = topology
        self.controller = controller
        self.jobs = jobs if jobs is not None else ConnectivityJobRegistry()

    def start(self, payload: ConnectivityStartRequest) -> str:
        """Validate the request, reserve a job, and start one worker thread."""
        topology, generation = self.topology.context()
        if not self.topology.gonetem_is_on():
            raise APIError(
                409,
                "GoNetEm is not running. Start containers first.",
            )
        if not self.topology.addressing_applied:
            raise APIError(
                409,
                "Apply addressing and routing before running connectivity checks.",
            )

        try:
            names = self.controller.resolve_connectivity_nodes(
                topology, payload.nodes
            )
        except ValueError as exc:
            raise APIError(422, str(exc)) from exc
        names = _deduplicate(names)
        if len(names) < 2:
            raise APIError(422, "At least two addressable nodes are required.")
        if len(names) > MAX_NODES:
            raise APIError(
                422,
                f"At most {MAX_NODES} nodes can be checked at once.",
            )
        pair_count = len(names) * (len(names) - 1)
        if pair_count > MAX_PAIRS:
            raise APIError(
                422,
                f"Connectivity checks are limited to {MAX_PAIRS} ordered pairs.",
            )

        runner = self.controller.run_connectivity_matrix

        try:
            job = self.jobs.create(
                nodes=names,
                ping_count=payload.ping_count,
                max_workers=payload.max_workers,
                flow_timeout_seconds=payload.flow_timeout_seconds,
                pair_count=pair_count,
                generation=generation,
            )
        except ConnectivityJobCapacityError as exc:
            raise APIError(429, str(exc)) from exc
        except Exception as exc:
            logger.exception("Failed to register a connectivity job.")
            raise APIError(
                500,
                "Failed to start connectivity check.",
            ) from exc

        thread = threading.Thread(
            target=self._run,
            args=(job, topology, names, runner),
            name=f"connectivity-{job.job_id}",
            daemon=True,
        )
        try:
            thread.start()
        except Exception as exc:
            logger.exception("Could not start the connectivity worker thread.")
            job.transition(
                "error",
                error="Failed to start connectivity check.",
            )
            raise APIError(
                500,
                "Failed to start connectivity check.",
            ) from exc
        return job.job_id

    def status(self, job_id: str) -> dict[str, Any]:
        """Return one job's current status or raise the common 404."""
        self.jobs.prune()
        job = self.jobs.get(job_id)
        if job is None:
            raise APIError(404, "Job not found.")
        return job.snapshot()

    def export(self, job_id: str, export_format: str) -> dict[str, Any]:
        """Return a finished job's matrix as CSV or JSON download content."""
        self.jobs.prune()
        job = self.jobs.get(job_id)
        if job is None:
            raise APIError(404, "Job not found.")

        snapshot = job.snapshot()
        if snapshot["status"] != "done":
            if snapshot["status"] == "running":
                raise APIError(
                    409,
                    "Connectivity check is still running.",
                )
            raise APIError(
                409,
                "Connectivity check failed; no results are available.",
            )

        if export_format == "csv":
            content = self._csv_content(snapshot["results"])
            extension = "csv"
            content_type = "text/csv"
        elif export_format == "json":
            content = json.dumps(
                {
                    "nodes": snapshot["nodes"],
                    "summary": snapshot["summary"],
                    "results": snapshot["results"],
                },
                indent=2,
            )
            extension = "json"
            content_type = "application/json"
        else:
            raise APIError(422, f"Unsupported export format: {export_format}")

        return {
            "ok": True,
            "filename": f"connectivity-{job.job_id}.{extension}",
            "content": content,
            "content_type": content_type,
        }

    def _run(
        self,
        job: ConnectivityJob,
        topology: Any,
        names: list[str],
        runner: Callable[..., dict[str, Any]],
    ) -> None:
        """Run one matrix and record a terminal state without crashing."""
        try:
            matrix = runner(
                topology,
                names,
                ping_count=job.ping_count,
                max_workers=job.max_workers,
                flow_timeout_seconds=job.flow_timeout_seconds,
            )
            if self.topology.generation != job.generation:
                job.transition(
                    "error",
                    error=("Project changed; connectivity results are no longer available."),
                )
                return
            if not isinstance(matrix, dict):
                raise RuntimeError("Connectivity check returned an invalid result.")
            summary = matrix.get("summary")
            results = matrix.get("results")
            if not isinstance(summary, dict) or not isinstance(results, list):
                raise RuntimeError("Connectivity check returned an invalid result.")
            job.transition("done", summary=summary, results=results)
        except Exception as exc:
            logger.exception("Connectivity check %s failed.", job.job_id)
            message = str(exc).strip() or "Connectivity check failed."
            job.transition("error", error=message[:500])

    @staticmethod
    def _csv_content(results: list[dict[str, Any]]) -> str:
        """Serialize results with the documented header and boolean casing."""
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(CSV_HEADER)
        for result in results:
            writer.writerow(
                [
                    result.get("source", ""),
                    result.get("destination", ""),
                    "true" if result.get("reachable") else "false",
                    result.get("packets_transmitted", ""),
                    result.get("packets_received", ""),
                    result.get("packet_loss_percent", ""),
                    result.get("rtt_min_ms", ""),
                    result.get("rtt_avg_ms", ""),
                    result.get("rtt_max_ms", ""),
                    result.get("error", ""),
                ]
            )
        return buffer.getvalue()
