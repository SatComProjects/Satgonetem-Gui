"""Unit tests for bounded topology snapshot history and comparison."""

from types import SimpleNamespace

import pytest

from satgonetem_gui.errors import APIError
from satgonetem_gui.services.topology_history_service import TopologyHistoryService


class FakeHistoryTopology:
    """Mutable topology reader used by the history service."""

    def __init__(self) -> None:
        self.step = 0
        self.time = "T0"
        self.generation = 1
        self.nodes_data = [
            {"name": "Sat0", "type": "satellite", "shell": "LEO", "city": None},
            {"name": "Sat1", "type": "satellite", "shell": "LEO", "city": None},
        ]
        self.links_data = [self._link("Sat0", "Sat1", capacity_kbps=100_000)]

    @staticmethod
    def _link(
        src: str,
        dst: str,
        *,
        capacity_kbps: int = 100_000,
        delay_ms: float = 1.0,
        is_active: bool = True,
    ) -> dict:
        return {
            "src": src,
            "dst": dst,
            "type": "InterSatelliteLink",
            "delay_ms": delay_ms,
            "capacity_kbps": capacity_kbps,
            "loss_percent": 0.0,
            "jitter_ms": 0,
            "is_active": is_active,
        }

    def context(self):
        return SimpleNamespace(current_time_step=self.step, current_time=self.time), self.generation

    def nodes(self):
        return list(self.nodes_data)

    def links(self):
        return list(self.links_data)


def _service():
    topology = FakeHistoryTopology()
    return TopologyHistoryService(topology), topology


def test_record_and_dedupe_by_step() -> None:
    service, topology = _service()

    first = service.record()
    second = service.record()

    assert first["recorded"] is True
    assert first["step"] == 0
    assert first["snapshot_count"] == 1
    assert second["recorded"] is False
    assert second["reason"] == "step unchanged"
    assert len(service.list_snapshots()["snapshots"]) == 1


def test_compare_reports_added_removed_and_changed_links() -> None:
    service, topology = _service()
    service.record()

    topology.step = 1
    topology.time = "T1"
    topology.links_data[0]["capacity_kbps"] = 50_000
    topology.links_data.append(topology._link("Sat1", "Gnd0", delay_ms=2.0))
    topology.nodes_data.append(
        {"name": "Gnd0", "type": "ground_station", "shell": None, "city": "Berlin"}
    )
    service.record()

    comparison = service.compare(0, 1)

    assert comparison["from"]["step"] == 0
    assert comparison["to"]["step"] == 1
    assert [(link["src"], link["dst"]) for link in comparison["added_links"]] == [("Sat1", "Gnd0")]
    assert comparison["changed_links"][0]["changes"] == ["capacity_kbps"]
    assert comparison["removed_links"] == []
    assert comparison["added_nodes"] == ["Gnd0"]
    assert comparison["removed_nodes"] == []


def test_compare_same_step_is_empty() -> None:
    service, _topology = _service()
    service.record()

    comparison = service.compare(0, 0)

    assert comparison["added_links"] == []
    assert comparison["removed_links"] == []
    assert comparison["changed_links"] == []
    assert comparison["added_nodes"] == []
    assert comparison["removed_nodes"] == []


def test_generation_change_clears_history() -> None:
    service, topology = _service()
    service.record()

    topology.generation = 2
    topology.step = 0
    service.record()

    snapshots = service.list_snapshots()["snapshots"]
    assert len(snapshots) == 1
    assert snapshots[0]["step"] == 0
    assert snapshots[0]["node_count"] == 2


def test_snapshot_ring_is_bounded() -> None:
    service, topology = _service()
    for step in range(TopologyHistoryService.MAX_SNAPSHOTS + 5):
        topology.step = step
        service.record()

    snapshots = service.list_snapshots()["snapshots"]

    assert len(snapshots) == TopologyHistoryService.MAX_SNAPSHOTS
    assert snapshots[0]["step"] == 5
    assert snapshots[-1]["step"] == TopologyHistoryService.MAX_SNAPSHOTS + 4


def test_unknown_compare_step_is_404() -> None:
    service, _topology = _service()
    service.record()

    with pytest.raises(APIError) as error:
        service.compare(0, 99)

    assert error.value.status_code == 404
    assert "not recorded" in error.value.message
