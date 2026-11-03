"""API behavior for the security lab before a project is loaded."""

from fastapi.testclient import TestClient

from satgonetem_gui.app import create_app


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
