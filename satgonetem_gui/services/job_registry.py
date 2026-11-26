"""Shared, thread-safe bounded storage for background job records.

Services own their job dataclasses; the registry only needs three accessors so
it can key, classify, and age them. Reservation support lets a service hold an
active slot while it validates a request before the job record exists.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Generic, TypeVar

JobT = TypeVar("JobT")

DEFAULT_MAX_JOBS = 100
DEFAULT_TTL_SECONDS = 3600.0


class JobCapacityError(RuntimeError):
    """Raised when the registry cannot make room for another job."""


def _job_id(job) -> str:
    return job.job_id


def _terminal(job) -> bool:
    return job.terminal


def _updated_at(job) -> float:
    return job.updated_at


@dataclass
class BoundedJobRegistry(Generic[JobT]):
    """Bounded job storage with terminal TTL pruning and optional active caps.

    Capacity rules:

    - ``max_jobs`` bounds the number of retained records; the oldest terminal
      record is evicted first.
    - ``max_active`` (when set) bounds records that have not reached a terminal
      state plus outstanding reservations.
    - terminal records older than ``ttl_seconds`` are pruned lazily.
    """

    max_jobs: int = DEFAULT_MAX_JOBS
    ttl_seconds: float = DEFAULT_TTL_SECONDS
    max_active: int | None = None
    clock: Callable[[], float] = time.time
    job_id: Callable[[JobT], str] = _job_id
    terminal: Callable[[JobT], bool] = _terminal
    updated_at: Callable[[JobT], float] = _updated_at
    _jobs: dict[str, JobT] = field(default_factory=dict, init=False, repr=False)
    _pending: int = field(default=0, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.max_jobs < 1:
            raise ValueError("max_jobs must be at least 1")
        if self.ttl_seconds < 0:
            raise ValueError("ttl_seconds must be non-negative")
        if self.max_active is not None and self.max_active < 1:
            raise ValueError("max_active must be at least 1")

    def __len__(self) -> int:
        with self._lock:
            return len(self._jobs)

    def create(self, job: JobT) -> JobT:
        """Register a job, making room first; raises when no capacity is left."""
        with self._lock:
            self._prune_locked(self.clock())
            self._require_active_slot_locked()
            self._make_room_locked()
            self._insert_locked(job)
        return job

    def reserve(self) -> None:
        """Reserve one active slot for a job that is not registered yet."""
        with self._lock:
            self._prune_locked(self.clock())
            self._require_active_slot_locked()
            self._pending += 1

    def release(self) -> None:
        """Release a reservation that never became a job."""
        with self._lock:
            if self._pending > 0:
                self._pending -= 1

    def commit(self, job: JobT) -> JobT:
        """Promote a reservation into a registered job."""
        with self._lock:
            self._make_room_locked()
            self._insert_locked(job)
            if self._pending > 0:
                self._pending -= 1
        return job

    def get(self, job_id: str) -> JobT | None:
        """Return one retained job by id."""
        with self._lock:
            return self._jobs.get(job_id)

    def running(self) -> list[JobT]:
        """Return a snapshot of the jobs that have not reached a terminal state."""
        with self._lock:
            return [job for job in self._jobs.values() if not self.terminal(job)]

    def prune(self) -> None:
        """Drop terminal jobs older than the TTL."""
        with self._lock:
            self._prune_locked(self.clock())

    def _require_active_slot_locked(self) -> None:
        if self.max_active is None:
            return
        active = self._pending + sum(
            1 for job in self._jobs.values() if not self.terminal(job)
        )
        if active >= self.max_active:
            raise JobCapacityError("Job limit reached.")

    def _make_room_locked(self) -> None:
        if len(self._jobs) < self.max_jobs:
            return
        self._evict_terminal_locked()
        if len(self._jobs) >= self.max_jobs:
            raise JobCapacityError("Job limit reached.")

    def _insert_locked(self, job: JobT) -> None:
        self._jobs[self.job_id(job)] = job

    def _prune_locked(self, now: float) -> None:
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if self.terminal(job) and now - self.updated_at(job) >= self.ttl_seconds
        ]
        for job_id in expired:
            del self._jobs[job_id]

    def _evict_terminal_locked(self) -> None:
        terminal = sorted(
            (job for job in self._jobs.values() if self.terminal(job)),
            key=self.updated_at,
        )
        while len(self._jobs) >= self.max_jobs and terminal:
            job = terminal.pop(0)
            self._jobs.pop(self.job_id(job), None)
