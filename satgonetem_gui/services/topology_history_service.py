"""Bounded in-memory topology snapshot history and comparison."""

import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..errors import APIError
from .topology_service import TopologyService


@dataclass(frozen=True)
class TopologySnapshot:
    """One recorded topology state."""

    step: int
    time: str | None
    recorded_at: str
    nodes: dict[str, dict[str, Any]]
    links: dict[str, dict[str, Any]]


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _link_key(src: str, dst: str) -> str:
    return "|".join(sorted((str(src), str(dst))))


def _link_record(link: dict[str, Any]) -> dict[str, Any]:
    return {
        "src": link.get("src", ""),
        "dst": link.get("dst", ""),
        "type": link.get("type", ""),
        "delay_ms": link.get("delay_ms", 0.0),
        "capacity_kbps": link.get("capacity_kbps", 0),
        "loss_percent": link.get("loss_percent", 0.0),
        "jitter_ms": link.get("jitter_ms", 0),
        "is_active": bool(link.get("is_active", True)),
    }


class TopologyHistoryService:
    """Record observed topology steps and diff two recorded snapshots."""

    MAX_SNAPSHOTS = 240
    MAX_LINK_RECORDS = 100_000

    def __init__(self, topology: TopologyService) -> None:
        self.topology = topology
        self._lock = threading.Lock()
        self._record_lock = threading.Lock()
        self._snapshots: deque[TopologySnapshot] = deque()
        self._generation: int | None = None

    def record(self) -> dict[str, Any]:
        """Record the current step once; repeated polls at the same step are no-ops."""
        # Serialize whole recordings so two concurrent polls cannot both pass
        # the dedupe check below and append the same step. Reads stay outside
        # ``_lock``; only listing/comparison requests use that lock.
        with self._record_lock:
            return self._record()

    def _record(self) -> dict[str, Any]:
        # Read observable state through the service boundary: the concrete
        # topology object is opaque to this service.
        status = self.topology.status()
        step = int(status.get("current_step") or 0)
        current_time = status.get("current_time")
        _topology, generation = self.topology.context()

        with self._lock:
            self._adopt_generation_locked(generation)
            if self._snapshots and self._snapshots[-1].step == step:
                return {
                    "ok": True,
                    "recorded": False,
                    "reason": "step unchanged",
                    "step": step,
                    "snapshot_count": len(self._snapshots),
                }

        # Expensive topology reads happen outside the lock so a large topology
        # does not serialize listing or comparison requests.
        nodes = {
            str(node["name"]): {
                "name": str(node["name"]),
                "type": node.get("type", ""),
                "city": node.get("city"),
                "shell": node.get("shell"),
            }
            for node in self.topology.nodes()
            if node.get("name")
        }
        links = {}
        for link in self.topology.links():
            if not link.get("src") or not link.get("dst"):
                continue
            links[_link_key(link["src"], link["dst"])] = _link_record(link)
        snapshot = TopologySnapshot(
            step=step,
            time=(str(current_time) if current_time else None),
            recorded_at=_utc_timestamp(),
            nodes=nodes,
            links=links,
        )

        with self._lock:
            if self.topology.generation != generation:
                # The project was replaced while the snapshot was collected;
                # drop the stale snapshot instead of recording mixed state.
                self._adopt_generation_locked(self.topology.generation)
                return {
                    "ok": True,
                    "recorded": False,
                    "reason": "project changed",
                    "step": step,
                    "snapshot_count": len(self._snapshots),
                }
            if self._snapshots and self._snapshots[-1].step == step:
                return {
                    "ok": True,
                    "recorded": False,
                    "reason": "step unchanged",
                    "step": step,
                    "snapshot_count": len(self._snapshots),
                }
            self._snapshots.append(snapshot)
            self._enforce_limits_locked()
            return {
                "ok": True,
                "recorded": True,
                "step": step,
                "snapshot_count": len(self._snapshots),
                "node_count": len(nodes),
                "link_count": len(links),
            }

    def list_snapshots(self) -> dict[str, Any]:
        """Return snapshot summaries newest last."""
        with self._lock:
            snapshots = [
                {
                    "step": snapshot.step,
                    "time": snapshot.time,
                    "recorded_at": snapshot.recorded_at,
                    "node_count": len(snapshot.nodes),
                    "link_count": len(snapshot.links),
                }
                for snapshot in self._snapshots
            ]
            return {
                "ok": True,
                "generation": self._generation,
                "snapshots": snapshots,
            }

    def compare(self, from_step: int, to_step: int) -> dict[str, Any]:
        """Diff two recorded steps by link key and node name."""
        with self._lock:
            before = self._find_locked(from_step)
            after = self._find_locked(to_step)
            added_links = [after.links[key] for key in sorted(set(after.links) - set(before.links))]
            removed_links = [
                before.links[key] for key in sorted(set(before.links) - set(after.links))
            ]
            changed_links = []
            for key in sorted(set(before.links) & set(after.links)):
                current = before.links[key]
                following = after.links[key]
                changes = [
                    field
                    for field in (
                        "type",
                        "delay_ms",
                        "capacity_kbps",
                        "loss_percent",
                        "jitter_ms",
                        "is_active",
                    )
                    if current.get(field) != following.get(field)
                ]
                if changes:
                    changed_links.append(
                        {
                            "src": following["src"],
                            "dst": following["dst"],
                            "before": current,
                            "after": following,
                            "changes": changes,
                        }
                    )
            return {
                "ok": True,
                "from": self._summary(before),
                "to": self._summary(after),
                "added_links": added_links,
                "removed_links": removed_links,
                "changed_links": changed_links,
                "added_nodes": sorted(set(after.nodes) - set(before.nodes)),
                "removed_nodes": sorted(set(before.nodes) - set(after.nodes)),
            }

    def _adopt_generation_locked(self, generation: int) -> None:
        """Reset recorded history when the loaded project generation changes."""
        if self._generation != generation:
            self._snapshots.clear()
            self._generation = generation

    def _find_locked(self, step: int) -> TopologySnapshot:
        for snapshot in self._snapshots:
            if snapshot.step == step:
                return snapshot
        raise APIError(404, f"Topology step {step} is not recorded.")

    @staticmethod
    def _summary(snapshot: TopologySnapshot) -> dict[str, Any]:
        return {
            "step": snapshot.step,
            "time": snapshot.time,
            "recorded_at": snapshot.recorded_at,
            "node_count": len(snapshot.nodes),
            "link_count": len(snapshot.links),
        }

    def _enforce_limits_locked(self) -> None:
        while len(self._snapshots) > self.MAX_SNAPSHOTS:
            self._snapshots.popleft()
        while (
            len(self._snapshots) > 1
            and sum(len(snapshot.links) for snapshot in self._snapshots) > self.MAX_LINK_RECORDS
        ):
            self._snapshots.popleft()
