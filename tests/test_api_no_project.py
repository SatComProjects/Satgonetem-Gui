"""Characterization tests for routes that require no loaded project."""

import pytest

from satgonetem_gui.state import app_state


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/api/satellites", None),
        ("GET", "/api/ground_stations", None),
        ("GET", "/api/links", None),
        ("GET", "/api/nodes", None),
        ("GET", "/api/nodes/Sat0", None),
        ("GET", "/api/routing/status", None),
        ("POST", "/api/routing/apply", {}),
        ("POST", "/api/routing/delete", None),
        ("POST", "/api/gonetem/start", None),
        ("POST", "/api/gonetem/stop", None),
        ("GET", "/api/traffic/nodes", None),
        ("POST", "/api/traffic/iperf3", {}),
        ("POST", "/api/traffic/ping", {}),
        ("POST", "/api/traffic/hping3", {}),
        ("GET", "/api/traffic/status?job_id=missing", None),
        ("POST", "/api/traffic/cancel", {}),
        ("GET", "/api/project/save", None),
        ("GET", "/api/project/config?name=Missing", None),
    ],
)
def test_project_dependent_routes_return_404(client, method: str, path: str, body) -> None:
    """Routes that need a topology report 404 before a project is loaded."""
    response = client.request(method, path, json=body)

    assert response.status_code == 404


def test_status_without_project_has_empty_counts(client) -> None:
    """The dashboard can poll status before a project is loaded."""
    response = client.get("/api/status")

    assert response.status_code == 200
    assert response.json() == {
        "constellation_loaded": False,
        "satellites": 0,
        "ground_stations": 0,
        "links": 0,
        "gonetem_is_on": False,
        "simulation_updating": False,
        "current_step": None,
        "current_time": None,
    }


def test_project_exists_is_false_without_project(client) -> None:
    """The create-page poll reports that no project is loaded."""
    response = client.get("/api/project/exists?name=Missing")

    assert response.status_code == 200
    assert response.json() == {"exists": False}


def test_ground_station_presets_are_served(client) -> None:
    """The preset endpoint exposes the bundled CSV files."""
    response = client.get("/api/ground_stations/presets")

    assert response.status_code == 200
    presets = response.json()
    assert presets
    assert {"name", "stations"} == set(presets[0])
    assert any(preset["name"] == "representative" for preset in presets)


def test_project_load_requires_content(client) -> None:
    """An empty load request is rejected."""
    response = client.post("/api/project/load", json={})

    assert response.status_code == 400
    assert response.json()["ok"] is False


@pytest.mark.xfail(
    strict=True,
    reason="D9: invalid JSON currently reaches the loader and returns 500; see #1",
)
def test_project_load_rejects_invalid_json_with_400(client) -> None:
    """Malformed project files should be a client error, not a server error."""
    response = client.post("/api/project/load", json={"content": "{not json"})

    assert response.status_code == 400


def test_project_create_rejects_invalid_json(client) -> None:
    """A body that is not JSON is rejected before any work starts."""
    response = client.post(
        "/api/project/create",
        content="not-json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400


def test_project_create_is_single_flight(client) -> None:
    """The current guard rejects a second request while a build is marked active."""
    app_state.creating = True

    response = client.post("/api/project/create", json={"name": "Second"})

    assert response.status_code == 409


def test_project_create_dispatches_a_background_build(client, monkeypatch) -> None:
    """The endpoint returns immediately after dispatching the build."""
    import satgonetem_gui.app as app_module

    received: list[dict] = []
    monkeypatch.setattr(app_module, "_build_topology", received.append)

    response = client.post("/api/project/create", json={"name": "Dispatched"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
