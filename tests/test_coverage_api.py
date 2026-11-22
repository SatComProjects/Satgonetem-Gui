"""API contract tests for coverage analytics."""

import pytest

pytestmark = pytest.mark.integration


class FakeCoverageController:
    """Deterministic coverage controller recording its inputs."""

    def __init__(self, error: Exception | None = None) -> None:
        self.calls = []
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
            "satellites": 100,
            "duration_ms": 2.5,
            "shells": [
                {
                    "identifier": "LEO",
                    "satellites": 100,
                    "coverage_percent": 37.5,
                }
            ],
            "ground_stations": [
                {
                    "name": "Berlin",
                    "covered": True,
                    "best_satellite": "Sat0",
                    "best_elevation_deg": 41.2,
                }
            ],
            "shells_truncated": False,
            "ground_stations_truncated": False,
        }


def test_coverage_snapshot_is_cached(project_client, services) -> None:
    """A snapshot returns the adapter payload and caches identical requests."""
    controller = FakeCoverageController()
    services.coverage.controller = controller

    response = project_client.post("/api/analysis/coverage", json={})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["coverage_percent"] == 37.5
    assert payload["satellites"] == 100
    assert payload["sampled_cells"] == 64_800
    assert payload["elevation_deg"] == 10.0
    assert payload["grid_resolution_deg"] == 1.0
    assert payload["step"] == 0
    assert payload["generation"] >= 1
    assert payload["cached"] is False
    assert payload["shells"][0]["identifier"] == "LEO"
    assert payload["ground_stations"][0]["name"] == "Berlin"
    assert controller.calls[0]["max_shells"] > 0
    assert controller.calls[0]["max_ground_stations"] > 0

    again = project_client.post("/api/analysis/coverage", json={})

    assert again.status_code == 200
    assert again.json()["cached"] is True
    assert len(controller.calls) == 1


def test_coverage_rejects_a_grid_over_the_work_cap(project_client, services) -> None:
    """A fine grid over 100 satellites is rejected before the adapter runs."""
    controller = FakeCoverageController()
    services.coverage.controller = controller

    response = project_client.post(
        "/api/analysis/coverage",
        json={"grid_resolution_deg": 0.25},
    )

    assert response.status_code == 422
    assert "coarser" in response.json()["error"].lower()
    assert controller.calls == []


@pytest.mark.parametrize(
    "body",
    [
        {"elevation_deg": -1},
        {"elevation_deg": 91},
        {"grid_resolution_deg": 0.1},
        {"grid_resolution_deg": 20},
    ],
)
def test_coverage_schema_bounds(project_client, body: dict) -> None:
    """Elevation and grid bounds are enforced before the service runs."""
    response = project_client.post("/api/analysis/coverage", json=body)

    assert response.status_code == 422
    assert response.json()["ok"] is False
