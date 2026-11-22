"""Unit and API tests for preflight checks and project estimates."""

import json

import pytest

from satgonetem_gui.errors import APIError
from satgonetem_gui.schemas import PreflightRequest
from satgonetem_gui.services.preflight_service import (
    ESTIMATED_MB_PER_CONTAINER,
    PreflightService,
    estimate_project,
)
from tests.factories import ground_object, project_payload, walker_shell


def _check(status: str, check_id: str = "storage") -> dict:
    return {
        "id": check_id,
        "label": check_id.title(),
        "status": status,
        "message": f"{check_id} is {status}.",
        "hint": None,
    }


class FakeDoctor:
    """Environment doctor with a fixed check list or a forced failure."""

    def __init__(self, checks=None, error: Exception | None = None) -> None:
        self.checks = checks if checks is not None else [_check("ok")]
        self.error = error

    def environment_checks(self):
        if self.error is not None:
            raise self.error
        return self.checks


def _payload_data() -> tuple[list, list]:
    payload = project_payload()
    return (
        json.loads(payload["walker_shells_json"]),
        json.loads(payload["ground_objects_properties_json"]),
    )


def test_estimate_counts_satellites_ground_stations_and_containers() -> None:
    """The 10x10 fixture plus one station is 101 containers."""
    shells, grounds = _payload_data()

    estimate = estimate_project(shells, grounds)

    assert estimate["satellites"] == 100
    assert estimate["ground_stations"] == 1
    assert estimate["containers"] == 101
    assert estimate["estimated_memory_mb"] == 101 * ESTIMATED_MB_PER_CONTAINER
    assert "rough" in estimate["note"].lower()
    assert str(ESTIMATED_MB_PER_CONTAINER) in estimate["note"]
    assert estimate["warnings"] == []


def test_estimate_warns_about_data_file_ground_objects() -> None:
    """A data_file station list is unknown until the core reads the file."""
    ground = ground_object()
    ground.pop("stations")
    ground["data_file"] = "stations.txt"

    estimate = estimate_project([walker_shell()], [ground])

    assert estimate["ground_stations"] == 0
    assert estimate["containers"] == 100
    assert any("data_file" in warning for warning in estimate["warnings"])


def test_estimate_warns_about_large_constellations() -> None:
    """More than 200 containers carries a size warning."""
    estimate = estimate_project([walker_shell(planes=20, satellites_per_plane=20)], [])

    assert estimate["containers"] == 400
    assert any("large" in warning.lower() for warning in estimate["warnings"])


@pytest.mark.parametrize(
    ("shells", "grounds"),
    [
        ("not-a-list", []),
        ([], "not-a-list"),
        (["not-an-object"], []),
        ([], ["not-an-object"]),
        (
            [
                {
                    "constellation_property": {
                        "amount_of_orbit_plane": 2,
                    }
                }
            ],
            [],
        ),
        (
            [
                {
                    "constellation_property": {
                        "amount_of_orbit_plane": -1,
                        "amount_of_satellite_per_orbit_plane": 10,
                    }
                }
            ],
            [],
        ),
        (
            [
                {
                    "constellation_property": {
                        "amount_of_orbit_plane": 1.5,
                        "amount_of_satellite_per_orbit_plane": 10,
                    }
                }
            ],
            [],
        ),
        (
            [
                {
                    "constellation_property": {
                        "amount_of_orbit_plane": "10",
                        "amount_of_satellite_per_orbit_plane": 10,
                    }
                }
            ],
            [],
        ),
        ([], [{"stations": "not-a-list"}]),
    ],
)
def test_estimate_rejects_malformed_input(shells, grounds) -> None:
    """Malformed constellation descriptions are client errors."""
    with pytest.raises(ValueError):
        estimate_project(shells, grounds)


def test_preflight_reports_checks_without_an_estimate() -> None:
    """Checks are returned when no project payload was submitted."""
    checks = [_check("ok"), _check("warning", "gonetem")]
    service = PreflightService(FakeDoctor(checks))

    result = service.run(None)

    assert result == {
        "ok": True,
        "blocking": False,
        "checks": checks,
        "estimate": None,
    }


def test_preflight_errors_are_blocking_but_transport_ok() -> None:
    """A blocking environment keeps the transport-level success flag true."""
    service = PreflightService(FakeDoctor([_check("error")]))

    result = service.run(None)

    assert result["ok"] is True
    assert result["blocking"] is True


def test_preflight_estimates_a_submitted_payload() -> None:
    """A submitted project is estimated from its JSON fields."""
    payload = project_payload()
    service = PreflightService(FakeDoctor())

    result = service.run(
        PreflightRequest(
            walker_shells_json=payload["walker_shells_json"],
            ground_objects_properties_json=payload["ground_objects_properties_json"],
        )
    )

    assert result["estimate"]["satellites"] == 100
    assert result["estimate"]["containers"] == 101


def test_preflight_treats_empty_json_fields_as_empty_lists() -> None:
    """An empty hidden field means an empty list, not a malformed payload."""
    service = PreflightService(FakeDoctor())

    result = service.run(PreflightRequest(walker_shells_json=""))

    assert result["estimate"] is not None
    assert result["estimate"]["containers"] == 0


def test_preflight_rejects_malformed_json() -> None:
    """Malformed estimate JSON is a 422 instead of a 500."""
    service = PreflightService(FakeDoctor())

    with pytest.raises(APIError) as error:
        service.run(PreflightRequest(walker_shells_json="not-json"))

    assert error.value.status_code == 422
    assert "valid JSON" in error.value.message


def test_preflight_rejects_non_array_json() -> None:
    """The hidden fields must contain JSON arrays."""
    service = PreflightService(FakeDoctor())

    with pytest.raises(APIError) as error:
        service.run(PreflightRequest(ground_objects_properties_json='{"a": 1}'))

    assert error.value.status_code == 422
    assert "JSON array" in error.value.message


def test_preflight_doctor_failure_is_a_500() -> None:
    """An unexpected doctor failure is logged and reported as a server error."""
    service = PreflightService(FakeDoctor(error=RuntimeError("boom")))

    with pytest.raises(APIError) as error:
        service.run(None)

    assert error.value.status_code == 500


def test_preflight_api_uses_the_injected_doctor(client, services) -> None:
    """The API returns the injected checks without touching real Docker."""
    checks = [
        _check("ok", "storage"),
        _check("warning", "docker"),
        _check("unknown", "images"),
        _check("warning", "gonetem"),
    ]
    services.preflight.doctor = FakeDoctor(checks)

    response = client.post("/api/diagnostics/preflight")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "ok": True,
        "blocking": False,
        "checks": checks,
        "estimate": None,
    }


def test_preflight_api_reports_blocking_with_http_200(client, services) -> None:
    """A blocking environment is still a successful 200 response for the UI."""
    services.preflight.doctor = FakeDoctor([_check("error", "storage")])

    response = client.post("/api/diagnostics/preflight")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ok"] is True
    assert data["blocking"] is True
    assert [check["id"] for check in data["checks"]] == ["storage"]
