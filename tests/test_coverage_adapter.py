"""Adapter tests for coverage snapshots."""

from types import SimpleNamespace

import pytest

from satgonetem_gui.adapters import coverage_adapter
from satgonetem_gui.adapters.coverage_adapter import SatGoNetemCoverageAdapter


def _satellite(name: str, latitude: float, shell: str):
    return SimpleNamespace(
        name=name,
        position={
            "latitude": latitude,
            "longitude": 0.0,
            "altitude": 550.0,
        },
        shell=SimpleNamespace(identifier=shell),
    )


def _station(name: str):
    return SimpleNamespace(
        name=name,
        position={"latitude": 0.0, "longitude": 0.0, "altitude": 0.0},
    )


class FakeCoverageTopology:
    """Topology double exposing the public coverage method."""

    def __init__(self, satellites, stations) -> None:
        self.satellites = {satellite.name: satellite for satellite in satellites}
        self.ground_stations = {station.name: station for station in stations}
        self.coverage_calls = []

    def get_coverage_percentage(self, *, elev_min_deg, grid_res_deg):
        self.coverage_calls.append((elev_min_deg, grid_res_deg))
        return 42.5


def _install_fakes(monkeypatch, *, shell_values=None):
    calls = {"fast": [], "elevation": 0}

    def fake_fast(*, sats, elev_min_deg, grid_res_deg):
        calls["fast"].append((len(sats), elev_min_deg, grid_res_deg))
        if shell_values is None:
            return 42.5
        identifier = sats[0].shell.identifier
        return shell_values[identifier]

    def fake_elevation(sat_coordinates, gnd_coordinates):
        calls["elevation"] += 1
        return 50.0 if sat_coordinates[0] == 10.0 else 5.0

    monkeypatch.setattr(coverage_adapter, "coverage_percentage_fast", fake_fast)
    monkeypatch.setattr(coverage_adapter, "get_elevation_angle", fake_elevation)
    return calls


def test_coverage_adapter_reports_shells_and_ground_stations(monkeypatch) -> None:
    """The adapter groups shells and finds the best satellite per station."""
    topology = FakeCoverageTopology(
        [
            _satellite("Sat0", 10.0, "LEO"),
            _satellite("Sat1", 20.0, "MEO"),
        ],
        [_station("Berlin"), _station("Oslo")],
    )
    calls = _install_fakes(
        monkeypatch,
        shell_values={"LEO": 10.0, "MEO": 20.0},
    )

    result = SatGoNetemCoverageAdapter().coverage_snapshot(
        topology,
        elevation_deg=10.0,
        grid_resolution_deg=1.0,
        include_shells=True,
        include_ground_stations=True,
        max_shells=24,
        max_ground_stations=64,
    )

    assert result["coverage_percent"] == 42.5
    assert result["satellites"] == 2
    assert result["duration_ms"] >= 0
    assert topology.coverage_calls == [(10.0, 1.0)]
    assert result["shells"] == [
        {"identifier": "LEO", "satellites": 1, "coverage_percent": 10.0},
        {"identifier": "MEO", "satellites": 1, "coverage_percent": 20.0},
    ]
    assert result["ground_stations"] == [
        {
            "name": "Berlin",
            "covered": True,
            "best_satellite": "Sat0",
            "best_elevation_deg": 50.0,
        },
        {
            "name": "Oslo",
            "covered": True,
            "best_satellite": "Sat0",
            "best_elevation_deg": 50.0,
        },
    ]
    assert result["shells_truncated"] is False
    assert result["ground_stations_truncated"] is False
    assert calls["elevation"] == 4


def test_coverage_adapter_respects_elevation_mask(monkeypatch) -> None:
    """A station is uncovered when its best elevation is under the mask."""
    topology = FakeCoverageTopology(
        [_satellite("Sat0", 10.0, "LEO")],
        [_station("Berlin")],
    )
    _install_fakes(monkeypatch, shell_values={"LEO": 10.0})

    result = SatGoNetemCoverageAdapter().coverage_snapshot(
        topology,
        elevation_deg=60.0,
        grid_resolution_deg=1.0,
        include_shells=False,
        include_ground_stations=True,
        max_shells=24,
        max_ground_stations=64,
    )

    assert result["shells"] == []
    assert result["ground_stations"][0]["covered"] is False


def test_coverage_adapter_truncates_shells_and_stations(monkeypatch) -> None:
    """Shell and station caps are reported as truncation."""
    topology = FakeCoverageTopology(
        [
            _satellite("Sat0", 10.0, "LEO"),
            _satellite("Sat1", 20.0, "MEO"),
        ],
        [_station("Berlin"), _station("Oslo")],
    )
    _install_fakes(
        monkeypatch,
        shell_values={"LEO": 10.0, "MEO": 20.0},
    )

    result = SatGoNetemCoverageAdapter().coverage_snapshot(
        topology,
        elevation_deg=10.0,
        grid_resolution_deg=1.0,
        include_shells=True,
        include_ground_stations=True,
        max_shells=1,
        max_ground_stations=1,
    )

    assert [shell["identifier"] for shell in result["shells"]] == ["LEO"]
    assert len(result["ground_stations"]) == 1
    assert result["shells_truncated"] is True
    assert result["ground_stations_truncated"] is True


def test_coverage_adapter_skips_satellites_without_positions(monkeypatch) -> None:
    """A satellite without a position is counted but not used for elevation."""
    missing = SimpleNamespace(name="SatX", position={}, shell=SimpleNamespace(identifier="LEO"))
    topology = FakeCoverageTopology(
        [_satellite("Sat0", 10.0, "LEO"), missing],
        [_station("Berlin")],
    )
    calls = _install_fakes(monkeypatch, shell_values={"LEO": 10.0})

    result = SatGoNetemCoverageAdapter().coverage_snapshot(
        topology,
        elevation_deg=10.0,
        grid_resolution_deg=1.0,
        include_shells=True,
        include_ground_stations=True,
        max_shells=24,
        max_ground_stations=64,
    )

    assert result["satellites"] == 2
    assert result["ground_stations"][0]["best_satellite"] == "Sat0"
    assert calls["elevation"] == 1


@pytest.mark.parametrize(
    ("include_shells", "include_stations"),
    [(False, False), (True, False), (False, True)],
)
def test_coverage_adapter_honors_include_toggles(
    monkeypatch,
    include_shells: bool,
    include_stations: bool,
) -> None:
    """Disabled sections are omitted without calling their helpers."""
    topology = FakeCoverageTopology(
        [_satellite("Sat0", 10.0, "LEO")],
        [_station("Berlin")],
    )
    calls = _install_fakes(monkeypatch, shell_values={"LEO": 10.0})

    result = SatGoNetemCoverageAdapter().coverage_snapshot(
        topology,
        elevation_deg=10.0,
        grid_resolution_deg=1.0,
        include_shells=include_shells,
        include_ground_stations=include_stations,
        max_shells=24,
        max_ground_stations=64,
    )

    if include_shells:
        assert [shell["identifier"] for shell in result["shells"]] == ["LEO"]
    else:
        assert result["shells"] == []
    if include_stations:
        assert [station["name"] for station in result["ground_stations"]] == ["Berlin"]
    else:
        assert result["ground_stations"] == []
    assert bool(calls["fast"]) is include_shells
    assert bool(calls["elevation"]) is include_stations
