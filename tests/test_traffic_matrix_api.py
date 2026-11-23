"""API contract tests for the throughput matrix."""

import time

import pytest

from tests.test_traffic_matrix import FakeMatrixTopology, FakeMatrixTraffic

pytestmark = pytest.mark.integration


def _wait_for_matrix(client, job_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    status = None
    while time.monotonic() < deadline:
        response = client.get(f"/api/traffic/matrix/{job_id}")
        assert response.status_code == 200, response.text
        status = response.json()
        if status["status"] != "running":
            return status
        time.sleep(0.01)
    raise AssertionError(status)


def test_matrix_start_status_and_export(project_client, services) -> None:
    """A fake pair runner fills the matrix and both export formats."""
    services.traffic_matrix.topology = FakeMatrixTopology()
    services.traffic_matrix.traffic = FakeMatrixTraffic()

    started = project_client.post(
        "/api/traffic/matrix",
        json={"nodes": ["Gnd0", "Gnd1"], "duration_s": 1},
    )
    assert started.status_code == 200, started.text
    job_id = started.json()["job_id"]

    status = _wait_for_matrix(project_client, job_id)
    assert status["status"] == "done"
    assert status["nodes"] == ["Gnd0", "Gnd1"]
    assert status["matrix"] == [[None, 10.0], [10.0, None]]
    assert status["pairs_completed"] == 2

    csv = project_client.get(f"/api/traffic/matrix/{job_id}/export?format=csv")
    assert csv.status_code == 200
    assert csv.json()["filename"].endswith(".csv")
    assert "Gnd0,Gnd1,10.0,done" in csv.json()["content"]

    unknown = project_client.get("/api/traffic/matrix/missing")
    assert unknown.status_code == 404


def test_matrix_requires_running_containers(project_client) -> None:
    """The real topology has no containers in the default suite."""
    response = project_client.post(
        "/api/traffic/matrix",
        json={"nodes": ["Gnd0", "Gnd1"]},
    )

    assert response.status_code == 409
    assert "GoNetEm" in response.json()["error"]


def test_matrix_bounds_and_capacity(project_client, services) -> None:
    """Schema and service bounds are enforced before work starts."""
    services.traffic_matrix.topology = FakeMatrixTopology()
    services.traffic_matrix.traffic = FakeMatrixTraffic()

    too_many = project_client.post(
        "/api/traffic/matrix",
        json={"nodes": [f"Gnd{index}" for index in range(13)]},
    )
    assert too_many.status_code == 422

    one = project_client.post(
        "/api/traffic/matrix",
        json={"nodes": ["Gnd0"]},
    )
    assert one.status_code == 422

    duplicate = project_client.post(
        "/api/traffic/matrix",
        json={"nodes": ["Gnd0", "Gnd0"]},
    )
    assert duplicate.status_code == 422
