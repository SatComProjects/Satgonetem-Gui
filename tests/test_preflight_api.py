"""API characterization tests for preflight diagnostics and build phases."""

from tests.factories import project_payload


def test_preflight_reports_environment_checks(client) -> None:
    """Preflight works without a loaded project and reports every check."""
    response = client.post("/api/diagnostics/preflight")

    assert response.status_code == 200, response.text
    data = response.json()
    assert isinstance(data["ok"], bool)
    assert isinstance(data["blocking"], bool)
    assert {check["id"] for check in data["checks"]} == {
        "storage",
        "docker",
        "images",
        "gonetem",
    }
    for check in data["checks"]:
        assert check["status"] in {"ok", "warning", "error", "unknown"}
        assert check["label"]
        assert check["message"]


def test_preflight_estimates_the_submitted_constellation(client) -> None:
    """The estimate counts satellites, ground stations, and containers."""
    payload = project_payload()

    response = client.post(
        "/api/diagnostics/preflight",
        json={
            "walker_shells_json": payload["walker_shells_json"],
            "ground_objects_properties_json": payload["ground_objects_properties_json"],
        },
    )

    assert response.status_code == 200, response.text
    estimate = response.json()["estimate"]
    assert estimate["satellites"] == 100
    assert estimate["ground_stations"] == 1
    assert estimate["containers"] == 101
    assert estimate["estimated_memory_mb"] > 0
    assert "rough" in estimate["note"].lower()


def test_preflight_rejects_malformed_project_json(client) -> None:
    """A malformed estimate payload is a client error, not a 500."""
    response = client.post(
        "/api/diagnostics/preflight",
        json={"walker_shells_json": "not-json"},
    )

    assert response.status_code == 422


def test_project_status_exposes_honest_phase_progress(client) -> None:
    """Idle status has explicit phase fields and no synthetic percentage."""
    response = client.get("/api/project/status")

    assert response.status_code == 200
    data = response.json()
    assert data["phase"] == "idle"
    assert data["progress"] is None
    assert data["started_at"] is None
    assert data["finished_at"] is None
    assert data["elapsed_ms"] is None
