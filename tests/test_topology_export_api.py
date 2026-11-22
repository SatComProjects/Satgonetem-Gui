"""API contract tests for topology health and exports."""

import json

import pytest

pytestmark = pytest.mark.integration


def test_topology_health_and_exports(project_client) -> None:
    """Health findings and all three exports share one topology snapshot."""
    health_response = project_client.get("/api/topology/health")

    assert health_response.status_code == 200, health_response.text
    health = health_response.json()
    assert health["ok"] is True
    assert health["nodes"] == 101
    assert health["links"] > 0
    assert isinstance(health["healthy"], bool)
    check_ids = {check["id"] for check in health["checks"]}
    assert check_ids == {
        "isolated_nodes",
        "missing_positions",
        "duplicate_positions",
        "zero_capacity_links",
        "negative_delay_links",
        "self_links",
        "duplicate_links",
    }
    assert all(check["severity"] in {"info", "warning"} for check in health["checks"])

    json_response = project_client.get("/api/topology/export?format=json")

    assert json_response.status_code == 200, json_response.text
    export = json_response.json()
    assert export["ok"] is True
    assert export["filename"] == "topology.json"
    assert export["content_type"] == "application/json"
    payload = json.loads(export["content"])
    assert payload["schema"] == "satgonetem-gui.topology/1"
    assert len(payload["nodes"]) == health["nodes"]
    assert len(payload["links"]) == health["links"]

    dot = project_client.get("/api/topology/export?format=dot").json()
    assert dot["filename"] == "topology.dot"
    assert dot["content_type"] == "text/vnd.graphviz"
    assert dot["content"].startswith("graph topology {")

    graphml = project_client.get("/api/topology/export?format=graphml").json()
    assert graphml["filename"] == "topology.graphml"
    assert graphml["content_type"] == "application/graphml+xml"
    assert graphml["content"].lstrip().startswith("<?xml")
    assert "<graphml" in graphml["content"]


def test_topology_export_rejects_unknown_format(project_client) -> None:
    """The query enum rejects unsupported export formats."""
    response = project_client.get("/api/topology/export?format=pdf")

    assert response.status_code == 422


def test_topology_export_enforces_the_size_cap(project_client, monkeypatch) -> None:
    """Oversized envelopes are a 422 instead of a huge response."""
    monkeypatch.setattr(
        "satgonetem_gui.services.topology_export_service.MAX_EXPORT_CHARS",
        10,
    )

    response = project_client.get("/api/topology/export?format=dot")

    assert response.status_code == 422
    assert "too large" in response.json()["error"].lower()
