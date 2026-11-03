"""API behavior for telemetry and alert routes."""

from fastapi.testclient import TestClient

from satgonetem_gui.app import create_app


def test_telemetry_requires_a_project(client) -> None:
    """Telemetry sampling needs a loaded topology."""
    response = client.get("/api/security/telemetry")

    assert response.status_code == 404


def test_clear_alerts_without_project(client) -> None:
    """Clearing the in-memory alert list is safe before a project loads."""
    response = client.post("/api/security/telemetry/clear-alerts")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_telemetry_requires_running_containers(project_client) -> None:
    """A loaded but stopped range cannot be sampled."""
    response = project_client.get("/api/security/telemetry")

    assert response.status_code == 409


def test_telemetry_page_has_a_detection_unit(settings) -> None:
    """The security page exposes the telemetry unit."""
    with TestClient(create_app(settings=settings)) as client:
        response = client.get("/security")

    assert response.status_code == 200
    assert "Telemetry" in response.text
    assert "Detection alerts" in response.text


def test_prometheus_requires_a_project(client) -> None:
    """The scrape endpoint is project-dependent."""
    response = client.get("/api/security/telemetry/prometheus")

    assert response.status_code == 404
