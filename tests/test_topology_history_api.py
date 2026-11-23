"""API contract tests for topology snapshot history."""

import pytest

pytestmark = pytest.mark.integration


def test_snapshot_record_list_and_compare(project_client) -> None:
    """Recording is idempotent per step and comparisons are available."""
    first = project_client.post("/api/topology/snapshots")
    second = project_client.post("/api/topology/snapshots")

    assert first.status_code == 200, first.text
    assert first.json()["recorded"] is True
    assert first.json()["step"] == 0
    assert first.json()["snapshot_count"] == 1
    assert second.status_code == 200
    assert second.json()["recorded"] is False
    assert second.json()["reason"] == "step unchanged"

    listing = project_client.get("/api/topology/snapshots")
    assert listing.status_code == 200
    snapshots = listing.json()["snapshots"]
    assert len(snapshots) == 1
    assert snapshots[0]["step"] == 0
    assert snapshots[0]["node_count"] == 101

    comparison = project_client.get("/api/topology/compare?from_step=0&to_step=0")
    assert comparison.status_code == 200, comparison.text
    data = comparison.json()
    assert data["from"]["step"] == 0
    assert data["to"]["step"] == 0
    assert data["added_links"] == []
    assert data["removed_links"] == []
    assert data["changed_links"] == []


def test_unknown_compare_step_is_404(project_client) -> None:
    """Comparing an unrecorded step is a clear 404."""
    project_client.post("/api/topology/snapshots")

    response = project_client.get("/api/topology/compare?from_step=0&to_step=99")

    assert response.status_code == 404
    assert "not recorded" in response.json()["error"]


def test_snapshot_list_works_without_a_project(client) -> None:
    """The snapshot catalog is empty before a project is loaded."""
    response = client.get("/api/topology/snapshots")

    assert response.status_code == 200
    assert response.json()["snapshots"] == []
    assert response.json()["generation"] is None
