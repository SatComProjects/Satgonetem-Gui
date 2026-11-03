"""Characterization tests for routes that require no loaded project."""

import json
import threading
from types import SimpleNamespace

import pytest

from satgonetem_gui.state import ProjectResult, app_state
from tests.factories import project_payload
from tests.helpers import wait_for_project_state


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


def test_project_status_is_idle_without_project(client) -> None:
    """The create page can read an explicit idle state before starting."""
    response = client.get("/api/project/status")

    assert response.status_code == 200
    assert response.json() == {
        "state": "idle",
        "operation": None,
        "project_name": None,
        "pending_name": None,
        "loaded": False,
        "error": None,
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


def test_project_create_requires_a_name(client) -> None:
    """A create request without a name is rejected before a thread starts."""
    response = client.post("/api/project/create", json={})

    assert response.status_code == 400


def test_project_create_is_single_flight(client) -> None:
    """A second create request is rejected while a build is marked active."""
    assert app_state.project.begin("First", save_path="/tmp/first", operation="create")
    try:
        response = client.post("/api/project/create", json={"name": "Second"})
    finally:
        app_state.project.reset()

    assert response.status_code == 409


def test_project_create_dispatches_a_real_build(client) -> None:
    """A valid create request moves the session to loaded."""
    response = client.post("/api/project/create", json=project_payload("Phase1Created"))

    assert response.status_code == 200
    status = wait_for_project_state(client, {"loaded"})
    assert status["project_name"] == "Phase1Created"
    assert status["loaded"] is True
    exists = client.get("/api/project/exists?name=Phase1Created").json()
    assert exists == {"exists": True}


def test_concurrent_create_and_load_are_rejected(client, monkeypatch) -> None:
    """Create and load both participate in the single-flight guard."""
    import satgonetem_gui.app as app_module

    started = threading.Event()
    release = threading.Event()

    def blocking_create(payload: dict) -> ProjectResult:
        started.set()
        release.wait(timeout=5)
        return ProjectResult(
            SimpleNamespace(set_status=lambda _value: None),
            payload["name"],
            "",
        )

    monkeypatch.setattr(app_module, "_create_project", blocking_create)
    first = client.post("/api/project/create", json=project_payload("First"))
    assert first.status_code == 200
    assert started.wait(timeout=2)

    second = client.post("/api/project/create", json=project_payload("Second"))
    load = client.post("/api/project/load", json={"content": "{}"})
    release.set()

    assert second.status_code == 409
    assert load.status_code == 409
    status = wait_for_project_state(client, {"loaded"})
    assert status["project_name"] == "First"


def test_invalid_build_reports_error(client) -> None:
    """An invalid constellation ends in an explicit error instead of polling forever."""
    payload = project_payload("Broken")
    shell = json.loads(payload["walker_shells_json"])[0]
    shell["constellation_property"]["amount_of_orbit_plane"] = 1
    shell["constellation_property"]["amount_of_satellite_per_orbit_plane"] = 2
    payload["walker_shells_json"] = json.dumps([shell])

    response = client.post("/api/project/create", json=payload)

    assert response.status_code == 200
    status = wait_for_project_state(client, {"error"})
    assert status["state"] == "error"
    assert status["error"]
    assert status["pending_name"] is None
    assert status["loaded"] is False
    exists = client.get("/api/project/exists?name=Broken").json()
    assert exists == {"exists": False}
