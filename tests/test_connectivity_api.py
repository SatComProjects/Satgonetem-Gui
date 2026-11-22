"""API characterization tests for full-mesh connectivity checks."""

import time

import pytest

pytestmark = pytest.mark.integration


def test_connectivity_requires_a_project(client) -> None:
    """A connectivity check needs a loaded topology."""
    response = client.post("/api/diagnostics/connectivity", json={})

    assert response.status_code == 404


def test_connectivity_requires_running_containers(project_client) -> None:
    """Pings cannot run before GoNetEm is started."""
    response = project_client.post("/api/diagnostics/connectivity", json={})

    assert response.status_code == 409
    assert "GoNetEm" in response.json()["error"]


def test_connectivity_job_and_csv_export(project_client, services, monkeypatch) -> None:
    """A background matrix job reports results and exports CSV."""
    matrix = {
        "nodes": ["Sat0", "Sat1"],
        "summary": {"pairs": 2, "reachable": 1, "unreachable": 1},
        "results": [
            {
                "source": "Sat0",
                "destination": "Sat1",
                "reachable": True,
                "packets_transmitted": 3,
                "packets_received": 3,
                "packet_loss_percent": 0.0,
                "rtt_min_ms": 1.0,
                "rtt_avg_ms": 1.5,
                "rtt_max_ms": 2.0,
                "error": None,
            },
            {
                "source": "Sat1",
                "destination": "Sat0",
                "reachable": False,
                "packets_transmitted": 3,
                "packets_received": 0,
                "packet_loss_percent": 100.0,
                "rtt_min_ms": None,
                "rtt_avg_ms": None,
                "rtt_max_ms": None,
                "error": "no reply",
            },
        ],
    }

    class FakeConnectivity:
        def resolve_connectivity_nodes(self, _topology, names):
            return list(names or matrix["nodes"])

        def run_connectivity_matrix(self, *args, **kwargs):
            return matrix

    services.connectivity.controller = FakeConnectivity()
    monkeypatch.setattr(services.topology, "gonetem_is_on", lambda: True)
    services.topology.set_addressing_applied(True)

    started = project_client.post(
        "/api/diagnostics/connectivity",
        json={"nodes": ["Sat0", "Sat1"], "ping_count": 3},
    )
    assert started.status_code == 200, started.text
    job_id = started.json()["job_id"]

    status = None
    for _ in range(200):
        response = project_client.get(f"/api/diagnostics/connectivity/{job_id}")
        assert response.status_code == 200, response.text
        status = response.json()
        if status["status"] != "running":
            break
        time.sleep(0.01)

    assert status is not None
    assert status["status"] == "done", status
    assert status["summary"]["pairs"] == 2
    assert status["results"][0]["source"] == "Sat0"

    export = project_client.get(f"/api/diagnostics/connectivity/{job_id}/export?format=csv")
    assert export.status_code == 200, export.text
    data = export.json()
    assert data["filename"].endswith(".csv")
    assert "source,destination,reachable" in data["content"]
    assert "Sat0,Sat1,true" in data["content"]


def test_connectivity_unknown_job_is_404(project_client) -> None:
    """An unknown job id is a normal 404."""
    response = project_client.get("/api/diagnostics/connectivity/missing")

    assert response.status_code == 404
