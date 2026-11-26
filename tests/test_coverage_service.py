"""Unit tests for coverage analytics orchestration."""

from types import SimpleNamespace

import pytest

from satgonetem_gui.errors import APIError
from satgonetem_gui.schemas import CoverageRequest
from satgonetem_gui.services.coverage_service import CoverageService
from satgonetem_gui.services.topology_service import TopologyService
from satgonetem_gui.state import ProjectSession
from tests.service_fakes import FakeReader


class FakeCoverageTopology:
    """Topology double with configurable satellites, stations, and step."""

    def __init__(
        self,
        satellites: int = 3,
        ground_stations: int = 1,
        step: int = 0,
    ) -> None:
        self.satellites = {
            str(index): SimpleNamespace(
                name=f"Sat{index}",
                position={
                    "latitude": float(index),
                    "longitude": 0.0,
                    "altitude": 550.0,
                },
            )
            for index in range(satellites)
        }
        self.ground_stations = {
            str(index): SimpleNamespace(
                name=f"Gnd{index}",
                position={
                    "latitude": 0.0,
                    "longitude": 0.0,
                    "altitude": 0.0,
                },
            )
            for index in range(ground_stations)
        }
        self.current_time_step = step


class FakeCoverageController:
    """Coverage controller double with deterministic output."""

    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self.error = error

    def coverage_snapshot(
        self,
        topology,
        *,
        elevation_deg,
        grid_resolution_deg,
        include_shells,
        include_ground_stations,
        max_shells,
        max_ground_stations,
    ):
        self.calls.append(
            {
                "elevation_deg": elevation_deg,
                "grid_resolution_deg": grid_resolution_deg,
                "include_shells": include_shells,
                "include_ground_stations": include_ground_stations,
                "max_shells": max_shells,
                "max_ground_stations": max_ground_stations,
            }
        )
        if self.error is not None:
            raise self.error
        return {
            "coverage_percent": 37.5,
            "satellites": 3,
            "duration_ms": 2.5,
            "shells": [
                {
                    "identifier": "LEO",
                    "satellites": 3,
                    "coverage_percent": 37.5,
                }
            ],
            "ground_stations": [
                {
                    "name": "Gnd0",
                    "covered": True,
                    "best_satellite": "Sat0",
                    "best_elevation_deg": 41.2,
                }
            ],
            "shells_truncated": False,
            "ground_stations_truncated": False,
        }


def _coverage_service(
    controller: FakeCoverageController,
    *,
    satellites: int = 3,
    ground_stations: int = 1,
    step: int = 0,
):
    topology = FakeCoverageTopology(
        satellites=satellites,
        ground_stations=ground_stations,
        step=step,
    )
    session = ProjectSession()
    session.succeed(topology, "Coverage", "")
    service = CoverageService(TopologyService(session, FakeReader()), controller)
    return service, topology, session


def test_coverage_service_requires_a_project() -> None:
    """Coverage analysis needs a loaded topology."""
    service = CoverageService(
        TopologyService(ProjectSession(), FakeReader()),
        FakeCoverageController(),
    )

    with pytest.raises(APIError) as error:
        service.analyze(CoverageRequest())

    assert error.value.status_code == 404


def test_coverage_service_rejects_an_empty_constellation() -> None:
    """A project without satellites is a 422, not a 0% result."""
    service, _topology, _session = _coverage_service(
        FakeCoverageController(),
        satellites=0,
    )

    with pytest.raises(APIError) as error:
        service.analyze(CoverageRequest())

    assert error.value.status_code == 422
    assert "satellite" in error.value.message.lower()


def test_coverage_service_caches_by_step_and_options() -> None:
    """Identical snapshots reuse the cache; options and steps recompute."""
    controller = FakeCoverageController()
    service, topology, session = _coverage_service(controller)
    request = CoverageRequest()

    first = service.analyze(request)

    assert first["coverage_percent"] == 37.5
    assert first["sampled_cells"] == 64_800
    assert first["generation"] == session.generation
    assert first["cached"] is False
    assert controller.calls[0]["elevation_deg"] == 10.0
    assert controller.calls[0]["grid_resolution_deg"] == 1.0
    assert controller.calls[0]["max_shells"] > 0
    assert controller.calls[0]["max_ground_stations"] > 0

    second = service.analyze(request)
    assert second["cached"] is True
    assert len(controller.calls) == 1

    service.analyze(CoverageRequest(elevation_deg=20))
    assert len(controller.calls) == 2

    topology.current_time_step = 7
    third = service.analyze(request)
    assert third["cached"] is False
    assert third["step"] == 7
    assert len(controller.calls) == 3


def test_coverage_service_cache_is_generation_scoped() -> None:
    """A replacement project never reuses the previous project's snapshot."""
    controller = FakeCoverageController()
    service, _topology, session = _coverage_service(controller)
    request = CoverageRequest()
    service.analyze(request)

    session.succeed(FakeCoverageTopology(), "Replacement", "")
    result = service.analyze(request)

    assert result["cached"] is False
    assert len(controller.calls) == 2


def test_coverage_service_rejects_an_oversized_grid() -> None:
    """A grid whose satellite-cell work exceeds the cap is a 422."""
    controller = FakeCoverageController()
    service, _topology, _session = _coverage_service(controller, satellites=100)

    with pytest.raises(APIError) as error:
        service.analyze(CoverageRequest(grid_resolution_deg=0.25))

    assert error.value.status_code == 422
    assert "coarser" in error.value.message.lower()
    assert "100" in error.value.message
    assert controller.calls == []


def test_coverage_service_wraps_adapter_failures() -> None:
    """Adapter exceptions become the common 500 envelope."""
    controller = FakeCoverageController(error=RuntimeError("numpy exploded"))
    service, _topology, _session = _coverage_service(controller)

    with pytest.raises(APIError) as error:
        service.analyze(CoverageRequest())

    assert error.value.status_code == 500
    assert "coverage analysis failed" in error.value.message.lower()


def test_coverage_service_propagates_truncation_flags() -> None:
    """Adapter truncation flags and empty lists survive the service."""
    controller = FakeCoverageController()
    service, _topology, _session = _coverage_service(controller)
    original = controller.coverage_snapshot

    def truncated(*args, **kwargs):
        payload = original(*args, **kwargs)
        payload["shells_truncated"] = True
        payload["ground_stations_truncated"] = True
        return payload

    controller.coverage_snapshot = truncated

    result = service.analyze(CoverageRequest())

    assert result["shells_truncated"] is True
    assert result["ground_stations_truncated"] is True
