"""API characterization tests for satellite addressability."""

import pytest

pytestmark = pytest.mark.integration


def _traffic_names(client) -> set[str]:
    response = client.get("/api/traffic/nodes")
    assert response.status_code == 200
    return {node["name"] for node in response.json()["nodes"]}


def test_satellites_start_addressable_only_as_ground_endpoints(project_client) -> None:
    """The default project exposes ground stations, not satellites, as endpoints."""
    response = project_client.get("/api/satellites/addressable")

    assert response.status_code == 200
    data = response.json()
    assert data["addressable"] == []
    assert data["count"] == 0
    assert data["total"] == 100
    assert data["routing_refresh_required"] is False
    assert _traffic_names(project_client) == {"Gnd100"}


def test_enable_all_satellites_for_traffic(project_client) -> None:
    """A global toggle makes satellites selectable and reports the count."""
    response = project_client.post("/api/satellites/addressable", json={"enabled": True})

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["enabled"] is True
    assert data["updated"] == 100

    status = project_client.get("/api/satellites/addressable").json()
    assert status["count"] == 100
    assert set(status["addressable"]) == {f"Sat{index}" for index in range(100)}

    names = _traffic_names(project_client)
    assert "Gnd100" in names
    assert {"Sat0", "Sat42", "Sat99"} <= names

    detail = project_client.get("/api/nodes/Sat0").json()
    assert detail["node"]["addressable"] is True


def test_enable_one_satellite_for_traffic(project_client) -> None:
    """A per-node toggle exposes exactly one satellite endpoint."""
    response = project_client.post("/api/nodes/Sat7/addressable", json={"enabled": True})

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["name"] == "Sat7"
    assert data["addressable"] is True
    assert data["updated"] == 1

    assert _traffic_names(project_client) == {"Gnd100", "Sat7"}
    assert project_client.get("/api/nodes/Sat7").json()["node"]["addressable"] is True
    assert project_client.get("/api/nodes/Sat8").json()["node"]["addressable"] is False


def test_disable_all_satellites_restores_ground_only_endpoints(project_client) -> None:
    """Disabling addressability removes satellites from the endpoint list."""
    assert (
        project_client.post("/api/satellites/addressable", json={"enabled": True}).status_code
        == 200
    )

    response = project_client.post("/api/satellites/addressable", json={"enabled": False})

    assert response.status_code == 200, response.text
    assert response.json()["updated"] == 100
    assert project_client.get("/api/satellites/addressable").json()["count"] == 0
    assert _traffic_names(project_client) == {"Gnd100"}


def test_addressability_update_reports_routing_refresh(project_client, services) -> None:
    """When addressing is applied, the UI is told to re-apply routing."""
    services.topology.set_addressing_applied(True)

    response = project_client.post("/api/nodes/Sat1/addressable", json={"enabled": True})

    assert response.status_code == 200
    assert response.json()["routing_refresh_required"] is True
    assert (
        project_client.get("/api/satellites/addressable").json()["routing_refresh_required"] is True
    )


@pytest.mark.parametrize("name", ["Sat404", "Gnd100", "Satellite"])
def test_addressability_rejects_unknown_or_non_satellite_nodes(project_client, name: str) -> None:
    """Only real satellite names can be toggled."""
    response = project_client.post(f"/api/nodes/{name}/addressable", json={"enabled": True})

    assert response.status_code == 404
