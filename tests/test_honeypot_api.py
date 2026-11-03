"""API behavior for the honeypot routes."""

from fastapi.testclient import TestClient

from satgonetem_gui.app import create_app


def test_honeypot_start_requires_project(client) -> None:
    response = client.post("/api/security/honeypots", json={"node": "Gnd24", "port": 2222})

    assert response.status_code == 404


def test_honeypot_status_requires_project(client) -> None:
    response = client.get("/api/security/honeypots/Gnd24/2222")

    assert response.status_code == 404


def test_honeypot_stop_requires_project(client) -> None:
    response = client.post("/api/security/honeypots/Gnd24/2222/stop")

    assert response.status_code == 404


def test_honeypot_rejects_invalid_port(client) -> None:
    response = client.post("/api/security/honeypots", json={"node": "Gnd24", "port": 0})

    assert response.status_code == 422


def test_honeypot_page_has_a_control(settings) -> None:
    with TestClient(create_app(settings=settings)) as client:
        response = client.get("/security")

    assert response.status_code == 200
    assert "Decoy honeypot" in response.text
