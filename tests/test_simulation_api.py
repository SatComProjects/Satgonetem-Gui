"""API characterization tests for simulation transport controls."""

import pytest

pytestmark = pytest.mark.integration


def test_simulation_status_exposes_transport_metadata(project_client) -> None:
    """The dashboard status includes the total steps and playback rate."""
    response = project_client.get("/api/status")

    assert response.status_code == 200
    data = response.json()
    assert data["total_steps"] > 0
    assert data["simulation_rate"] == pytest.approx(1.0)
    assert data["last_simulation_error"] is None


def test_simulation_step_and_reset_advance_the_clock(project_client) -> None:
    """A single step advances the step counter and reset returns to zero."""
    step = project_client.post("/api/simulation/step")
    assert step.status_code == 200, step.text

    status = project_client.get("/api/status").json()
    assert status["current_step"] == 1

    reset = project_client.post("/api/simulation/reset")
    assert reset.status_code == 200, reset.text

    status = project_client.get("/api/status").json()
    assert status["current_step"] == 0


def test_simulation_start_and_stop_control_the_loop(project_client) -> None:
    """Start and stop are accepted and update the running flag."""
    start = project_client.post("/api/simulation/start")
    assert start.status_code == 200, start.text
    try:
        status = project_client.get("/api/status").json()
        assert status["simulation_updating"] is True
    finally:
        stop = project_client.post("/api/simulation/stop")
    assert stop.status_code == 200, stop.text
    assert project_client.get("/api/status").json()["simulation_updating"] is False


def test_simulation_speed_rejects_unknown_direction(project_client) -> None:
    """Only faster/slower are accepted playback directions."""
    response = project_client.post("/api/simulation/speed", json={"direction": "sideways"})

    assert response.status_code == 422


def test_simulation_seek_rejects_negative_step(project_client) -> None:
    """The seek target is a non-negative step index."""
    response = project_client.post("/api/simulation/seek", json={"step": -1})

    assert response.status_code == 422
