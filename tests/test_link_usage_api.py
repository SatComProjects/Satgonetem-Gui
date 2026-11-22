"""API tests for link usage sampling."""

import pytest

pytestmark = pytest.mark.integration


def test_link_usage_reports_unavailable_when_containers_are_stopped(
    project_client,
) -> None:
    """Usage is unavailable before GoNetEm is running, without failing the page."""
    response = project_client.get("/api/links/usage")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["available"] is False
    assert data["links"] == []
    assert "container" in data["note"].lower()
