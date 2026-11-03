"""API behavior for the security lab before a project is loaded."""

import json

from fastapi.testclient import TestClient

from satgonetem_gui.app import create_app
from tests.helpers import wait_for_project_state


def test_security_range_without_project_is_empty(client) -> None:
    """The page can render its empty state before a project is loaded."""
    response = client.get("/api/security/range")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["readiness"] == {
        "project_loaded": False,
        "gonetem_is_on": False,
        "addressing_applied": False,
        "routing_initiated": False,
        "routing_method": None,
    }
    assert data["nodes"] == []
    assert data["links"] == []
    assert data["captures"] == []


def test_security_preset_is_a_valid_create_payload(client) -> None:
    """The bundled range can be submitted directly to the project builder."""
    response = client.get("/api/security/preset")

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "SatSecRange"
    assert payload["isl_capacity"] == 5000
    assert payload["gs_capacity"] == 5000
    walkers = json.loads(payload["walker_shells_json"])
    grounds = json.loads(payload["ground_objects_properties_json"])
    assert walkers
    assert len(grounds[0]["stations"]) == 3


def test_security_preset_builds_a_range(client) -> None:
    """The bundled preset is accepted by the real project builder."""
    payload = client.get("/api/security/preset").json()

    response = client.post("/api/project/create", json=payload)
    assert response.status_code == 200
    status = wait_for_project_state(client, {"loaded"})
    assert status["project_name"] == "SatSecRange"

    range_data = client.get("/api/security/range").json()
    assert range_data["readiness"]["project_loaded"] is True
    assert len(range_data["links"]) > 0
    assert len(range_data["nodes"]) >= 3
    assert all(link["capacity_kbps"] == 5000 for link in range_data["links"])


def test_security_capture_start_requires_a_project(client) -> None:
    """Capture controls cannot start without a loaded topology."""
    response = client.post(
        "/api/security/captures",
        json={"node": "Sat0", "interface": "eth0"},
    )

    assert response.status_code == 404


def test_security_fail_link_requires_a_project(client) -> None:
    """Link failure is project-dependent."""
    response = client.post("/api/security/links/missing/fail")

    assert response.status_code == 404


def test_security_capture_rejects_invalid_limits(client) -> None:
    """Capture bounds are enforced before any container command runs."""
    response = client.post(
        "/api/security/captures",
        json={
            "node": "Sat0",
            "interface": "eth0",
            "packet_limit": 0,
            "duration_sec": 999,
        },
    )

    assert response.status_code == 422


def test_security_hping3_rejects_invalid_spoof_source(client) -> None:
    """A forged source must be a valid IPv4 address before a job starts."""
    response = client.post(
        "/api/traffic/hping3",
        json={
            "src": "Gnd0",
            "dst": "Gnd1",
            "spoof_src": "not-an-ip",
        },
    )

    assert response.status_code == 422


def test_security_reset_requires_a_snapshot(client) -> None:
    """Reset reports a conflict when no security snapshot exists."""
    response = client.post("/api/security/reset")

    assert response.status_code == 409


def test_security_captures_empty_without_project(client) -> None:
    """The capture list is safe to poll before a project is loaded."""
    response = client.get("/api/security/captures")

    assert response.status_code == 200
    assert response.json() == []


def test_security_download_missing_capture(client) -> None:
    """Unknown captures return the standard not-found envelope."""
    response = client.get("/api/security/captures/missing")

    assert response.status_code == 404
    assert response.json()["ok"] is False


def test_security_page_lists_the_five_units(settings) -> None:
    """The rendered security page exposes all five labs."""
    with TestClient(create_app(settings=settings)) as client:
        response = client.get("/security")

    assert response.status_code == 200
    for label in (
        "Reconnaissance",
        "Availability / DDoS",
        "Resilience",
        "Confidentiality",
        "Trust / spoofing",
    ):
        assert label in response.text
