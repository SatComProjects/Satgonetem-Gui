"""Unit tests for the shared bounded job registry."""

from dataclasses import dataclass

import pytest

from satgonetem_gui.services.job_registry import (
    BoundedJobRegistry,
    JobCapacityError,
)


@dataclass
class FakeJob:
    """Minimal job record exposing the registry's accessor surface."""

    job_id: str
    updated_at: float = 0.0
    terminal: bool = False


def _registry(**overrides):
    options = {"max_jobs": 10, "ttl_seconds": 3600.0}
    options.update(overrides)
    return BoundedJobRegistry[FakeJob](**options)


def test_create_get_and_running_snapshot() -> None:
    """Registered jobs are retrievable and classified by terminal state."""
    registry = _registry()
    active = FakeJob("a")
    done = FakeJob("b", terminal=True)

    assert registry.create(active) is active
    registry.create(done)

    assert registry.get("a") is active
    assert registry.get("missing") is None
    assert registry.running() == [active]
    assert len(registry) == 2


def test_total_capacity_rejects_a_new_job_while_slots_are_active() -> None:
    """Running jobs keep their records and cannot be evicted for capacity."""
    registry = _registry(max_jobs=1)
    registry.create(FakeJob("a"))

    with pytest.raises(JobCapacityError):
        registry.create(FakeJob("b"))


def test_finished_jobs_are_evicted_before_capacity_is_rejected() -> None:
    """The oldest terminal record frees the slot first."""
    registry = _registry(max_jobs=1)
    registry.create(FakeJob("old", updated_at=1.0, terminal=True))

    created = registry.create(FakeJob("new"))

    assert registry.get("old") is None
    assert registry.get("new") is created


def test_oldest_terminal_job_is_evicted_first() -> None:
    """Eviction order is by update timestamp, not insertion order."""
    registry = _registry(max_jobs=2, clock=lambda: 0.0)
    registry.create(FakeJob("newer", updated_at=20.0, terminal=True))
    registry.create(FakeJob("older", updated_at=10.0, terminal=True))

    registry.create(FakeJob("active"))

    assert registry.get("older") is None
    assert registry.get("newer") is not None


def test_active_slot_limit_is_independent_from_total_capacity() -> None:
    """A dedicated active cap rejects new work while retaining finished jobs."""
    registry = _registry(max_jobs=10, max_active=1)
    first = registry.create(FakeJob("first"))

    with pytest.raises(JobCapacityError):
        registry.create(FakeJob("second"))

    first.terminal = True
    registry.create(FakeJob("second"))
    assert registry.get("second") is not None


def test_reservation_holds_an_active_slot_until_commit_or_release() -> None:
    """Reservations protect capacity before the job record exists."""
    registry = _registry(max_jobs=10, max_active=1)

    registry.reserve()
    with pytest.raises(JobCapacityError):
        registry.reserve()
    with pytest.raises(JobCapacityError):
        registry.create(FakeJob("direct"))

    registry.release()
    registry.reserve()
    job = FakeJob("committed")
    assert registry.commit(job) is job
    assert registry.get("committed") is job
    with pytest.raises(JobCapacityError):
        registry.reserve()


def test_terminal_jobs_are_pruned_after_the_ttl() -> None:
    """A fake clock drives deterministic terminal-TTL pruning."""
    now = 0.0
    registry = _registry(ttl_seconds=10.0, clock=lambda: now)
    registry.create(FakeJob("job", updated_at=0.0, terminal=True))

    now = 9.0
    registry.prune()
    assert registry.get("job") is not None

    now = 10.0
    registry.prune()
    assert registry.get("job") is None


def test_running_jobs_are_never_pruned_by_ttl() -> None:
    """The TTL only applies to records that already reached a terminal state."""
    now = 0.0
    registry = _registry(ttl_seconds=10.0, clock=lambda: now)
    registry.create(FakeJob("running", updated_at=0.0))

    now = 1000.0
    registry.prune()

    assert registry.get("running") is not None


def test_invalid_configuration_is_rejected() -> None:
    """Bounded registries refuse configurations that cannot hold one job."""
    with pytest.raises(ValueError):
        _registry(max_jobs=0)
    with pytest.raises(ValueError):
        _registry(ttl_seconds=-1.0)
    with pytest.raises(ValueError):
        _registry(max_active=0)
