"""Bounded background throughput matrix over iperf3 pairs."""

import csv
import io
import json
import logging
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..errors import APIError
from ..schemas import Iperf3Request, TrafficMatrixRequest
from ..time_utils import utc_timestamp
from .topology_service import TopologyService
from .traffic_service import TrafficService

logger = logging.getLogger(__name__)

MAX_MATRIX_NODES = 12
MAX_PAIRS = MAX_MATRIX_NODES * (MAX_MATRIX_NODES - 1)
MAX_ACTIVE_JOBS = 2
MAX_JOBS = 20
TERMINAL_TTL_SECONDS = 3600.0
PAIR_POLL_INTERVAL_SECONDS = 0.25


@dataclass
class MatrixJob:
    """One bounded throughput matrix run."""

    job_id: str
    nodes: list[str]
    duration_s: int
    concurrency: int
    timeout_s: float
    generation: int
    status: str = "running"
    results: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=utc_timestamp)
    finished_at: str | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def pairs_total(self) -> int:
        return len(self.nodes) * (len(self.nodes) - 1)

    @property
    def pairs_completed(self) -> int:
        return len(self.results)


class TrafficMatrixService:
    """Run iperf3 between ordered node pairs with strict caps."""

    def __init__(
        self,
        topology: TopologyService,
        traffic: TrafficService,
        *,
        poll_interval: float = PAIR_POLL_INTERVAL_SECONDS,
        clock=time.time,
    ) -> None:
        self.topology = topology
        self.traffic = traffic
        self.poll_interval = poll_interval
        self.clock = clock
        self._jobs: dict[str, MatrixJob] = {}
        self._lock = threading.Lock()

    def start(self, payload: TrafficMatrixRequest) -> str:
        """Validate preconditions and start one background matrix."""
        _topology, generation = self.topology.context()
        if not self.topology.gonetem_is_on():
            raise APIError(409, "GoNetEm is not running.")
        if not self.topology.addressing_applied:
            raise APIError(409, "Apply addressing before running a matrix.")

        available = {str(node.get("name")) for node in self.traffic.nodes() if node.get("name")}
        requested = [str(name) for name in payload.nodes]
        if requested:
            if len(set(requested)) != len(requested):
                raise APIError(422, "Matrix nodes must be unique.")
            unknown = sorted(set(requested) - available)
            if unknown:
                raise APIError(422, f"Unknown traffic nodes: {', '.join(unknown)}")
            nodes = requested
        else:
            nodes = sorted(available)[:MAX_MATRIX_NODES]
        if len(nodes) < 2:
            raise APIError(422, "Select at least two traffic nodes.")
        if len(nodes) > MAX_MATRIX_NODES:
            raise APIError(
                422,
                f"At most {MAX_MATRIX_NODES} nodes can be compared.",
            )

        with self._lock:
            self._prune_locked()
            active = [job for job in self._jobs.values() if job.status == "running"]
            if len(active) >= MAX_ACTIVE_JOBS:
                raise APIError(429, "A throughput matrix is already running.")
            job_id = (
                f"mx-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{secrets.token_hex(4)}"
            )
            job = MatrixJob(
                job_id=job_id,
                nodes=nodes,
                duration_s=payload.duration_s,
                concurrency=payload.concurrency,
                timeout_s=payload.timeout_s,
                generation=generation,
                created_at=self.clock(),
                updated_at=self.clock(),
            )
            self._jobs[job_id] = job

        thread = threading.Thread(
            target=self._worker,
            args=(job,),
            name=f"traffic-matrix-{job_id}",
            daemon=True,
        )
        try:
            thread.start()
        except Exception:
            logger.exception("Could not start the traffic matrix worker.")
            self._finalize_error(job, "Matrix worker could not start.")
        return job_id

    def status(self, job_id: str) -> dict[str, Any]:
        """Return one matrix job snapshot, including matrix and flat results."""
        with self._lock:
            self._prune_locked()
            job = self._jobs.get(job_id)
            if job is None:
                raise APIError(404, "Matrix job not found.")
            with job.lock:
                return self._snapshot_locked(job)

    def export(self, job_id: str, export_format: str) -> dict[str, Any]:
        """Export one matrix as a CSV or JSON download envelope."""
        snapshot = self.status(job_id)
        if export_format == "csv":
            buffer = io.StringIO()
            writer = csv.writer(buffer, lineterminator="\n")
            writer.writerow(["src", "dst", "throughput_mbps", "status", "error"])
            for result in snapshot["results"]:
                writer.writerow(
                    [
                        result["src"],
                        result["dst"],
                        ("" if result["throughput_mbps"] is None else result["throughput_mbps"]),
                        result["status"],
                        result["error"] or "",
                    ]
                )
            return {
                "ok": True,
                "filename": f"traffic-matrix-{job_id}.csv",
                "content": buffer.getvalue(),
                "content_type": "text/csv",
            }
        if export_format == "json":
            payload = {
                "job_id": job_id,
                "nodes": snapshot["nodes"],
                "matrix": snapshot["matrix"],
                "results": snapshot["results"],
            }
            return {
                "ok": True,
                "filename": f"traffic-matrix-{job_id}.json",
                "content": json.dumps(payload, indent=2) + "\n",
                "content_type": "application/json",
            }
        raise ValueError(f"Unsupported matrix export format: {export_format}")

    def _worker(self, job: MatrixJob) -> None:
        try:
            pairs = [
                (source, destination)
                for source in job.nodes
                for destination in job.nodes
                if source != destination
            ]
            with ThreadPoolExecutor(max_workers=job.concurrency) as pool:
                futures = {
                    pool.submit(self._run_pair, job, source, destination): (
                        source,
                        destination,
                    )
                    for source, destination in pairs
                }
                for future in as_completed(futures):
                    source, destination = futures[future]
                    try:
                        result = future.result()
                    except Exception as exc:  # noqa: BLE001 - worker must not die
                        logger.exception("Matrix pair failed.")
                        result = {
                            "src": source,
                            "dst": destination,
                            "status": "error",
                            "throughput_mbps": None,
                            "error": str(exc) or "Pair failed.",
                        }
                    with job.lock:
                        job.results[(source, destination)] = result
                        job.updated_at = self.clock()
            with job.lock:
                job.status = "done"
                job.finished_at = utc_timestamp()
                job.updated_at = self.clock()
        except BaseException:  # noqa: BLE001 - keep the worker contained
            logger.exception("Traffic matrix worker failed.")
            with job.lock:
                job.status = "error"
                job.errors.append("Matrix worker stopped unexpectedly.")
                job.finished_at = utc_timestamp()
                job.updated_at = self.clock()

    def _run_pair(self, job: MatrixJob, source: str, destination: str) -> dict[str, Any]:
        if self.topology.generation != job.generation:
            return self._pair_error(source, destination, "Project changed; pair skipped.")
        request = Iperf3Request(
            src=source,
            dst=destination,
            duration=job.duration_s,
            interval=1,
            parallel=1,
        )
        try:
            flow_id = self.traffic.start("iperf3", request)
        except APIError as exc:
            return self._pair_error(source, destination, exc.message)
        except Exception as exc:  # noqa: BLE001 - one pair must not abort the job
            logger.exception("Could not start matrix pair %s->%s.", source, destination)
            return self._pair_error(source, destination, str(exc) or "Start failed.")

        deadline = time.monotonic() + job.timeout_s
        while time.monotonic() < deadline:
            try:
                snapshot = self.traffic.status(flow_id)
            except APIError as exc:
                return self._pair_error(source, destination, exc.message)
            except Exception as exc:  # noqa: BLE001 - keep polling other pairs
                return self._pair_error(source, destination, str(exc) or "Poll failed.")
            status = snapshot.get("status")
            if status == "done":
                results = snapshot.get("results") or {}
                throughput = results.get("avg_throughput_mbps")
                return {
                    "src": source,
                    "dst": destination,
                    "status": "done",
                    "throughput_mbps": (
                        round(float(throughput), 3)
                        if isinstance(throughput, (int, float))
                        else None
                    ),
                    "error": None,
                }
            if status in {"error", "cancelled"}:
                return self._pair_error(
                    source,
                    destination,
                    snapshot.get("error") or "Flow failed.",
                )
            time.sleep(self.poll_interval)
        self._cancel_timed_out_flow(flow_id, source, destination)
        return self._pair_error(source, destination, "Pair timed out.")

    def _cancel_timed_out_flow(self, flow_id: str, source: str, destination: str) -> None:
        """Best-effort stop of a flow whose pair exceeded its deadline."""
        try:
            self.traffic.cancel(flow_id)
        except APIError as exc:
            if exc.status_code != 409:
                logger.warning(
                    "Could not cancel the timed-out matrix pair %s->%s: %s",
                    source,
                    destination,
                    exc.message,
                )
        except Exception:
            logger.exception(
                "Could not cancel the timed-out matrix pair %s->%s.",
                source,
                destination,
            )

    def _finalize_error(self, job: MatrixJob, message: str) -> None:
        """Move a job that never reached the worker to a terminal error state."""
        with job.lock:
            job.status = "error"
            job.errors.append(message)
            job.finished_at = utc_timestamp()
            job.updated_at = self.clock()

    @staticmethod
    def _pair_error(source: str, destination: str, error: str) -> dict[str, Any]:
        return {
            "src": source,
            "dst": destination,
            "status": "error",
            "throughput_mbps": None,
            "error": error,
        }

    def _snapshot_locked(self, job: MatrixJob) -> dict[str, Any]:
        index = {name: position for position, name in enumerate(job.nodes)}
        matrix: list[list[float | None]] = [[None for _ in job.nodes] for _ in job.nodes]
        results = []
        for source in job.nodes:
            for destination in job.nodes:
                if source == destination:
                    continue
                result = job.results.get((source, destination))
                if result is None:
                    results.append(
                        {
                            "src": source,
                            "dst": destination,
                            "status": "pending",
                            "throughput_mbps": None,
                            "error": None,
                        }
                    )
                    continue
                results.append(result)
                matrix[index[source]][index[destination]] = result["throughput_mbps"]
        return {
            "ok": True,
            "job_id": job.job_id,
            "status": job.status,
            "nodes": list(job.nodes),
            "matrix": matrix,
            "results": results,
            "pairs_total": job.pairs_total,
            "pairs_completed": job.pairs_completed,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "errors": list(job.errors),
        }

    def _prune_locked(self) -> None:
        now = self.clock()
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.status != "running" and now - job.updated_at >= TERMINAL_TTL_SECONDS
        ]
        for job_id in expired:
            del self._jobs[job_id]
        ordered = sorted(self._jobs.values(), key=lambda job: job.created_at)
        while len(ordered) > MAX_JOBS:
            job = ordered.pop(0)
            if job.status != "running":
                self._jobs.pop(job.job_id, None)
