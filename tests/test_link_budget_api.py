"""API contract tests for the link-budget workbench."""

import pytest

pytestmark = pytest.mark.integration


def test_link_budget_works_without_a_project(client) -> None:
    """The workbench is independent of the loaded topology."""
    response = client.post("/api/analysis/link-budget", json={})

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ok"] is True
    assert data["direction"] == "downlink"
    assert data["strategy"] == "shannon"
    assert data["frequency_ghz"] == 19.0
    assert data["bandwidth_mhz"] == 500.0
    assert data["distance_km"] == 1000.0
    assert data["elevation_deg"] == 30.0
    assert data["capacity_kbps"] > 0
    assert data["capacity_mbps"] > 0
    assert data["eirp_db"] > 0
    assert data["g_over_t_db"] > 0
    assert data["fspl_db"] > 0
    assert data["cn0_dbhz"] > 0
    assert isinstance(data["atmospheric_available"], bool)


def test_link_budget_echoes_uplink_and_modcod(client) -> None:
    """Direction and capacity strategy are validated and echoed."""
    response = client.post(
        "/api/analysis/link-budget",
        json={
            "direction": "uplink",
            "strategy": "modcod",
            "frequency_ghz": 14.25,
            "bandwidth_mhz": 250,
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["direction"] == "uplink"
    assert data["strategy"] == "modcod"
    assert data["frequency_ghz"] == 14.25
    assert data["capacity_kbps"] >= 0


@pytest.mark.parametrize(
    "body",
    [
        {"frequency_ghz": 0},
        {"frequency_ghz": 1001},
        {"bandwidth_mhz": 0},
        {"distance_km": 0},
        {"elevation_deg": 91},
        {"gs_latitude": 91},
        {"satellite_antenna_efficiency": 0},
        {"satellite_antenna_efficiency": 1.5},
        {"rx_tsys_k": 0},
        {"unavailability_percent": 0},
    ],
)
def test_link_budget_bounds_are_422(client, body: dict) -> None:
    """All physical bounds are validated before the adapter runs."""
    response = client.post("/api/analysis/link-budget", json=body)

    assert response.status_code == 422
    assert response.json()["ok"] is False
