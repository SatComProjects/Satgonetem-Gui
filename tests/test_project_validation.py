"""Validation of the nested project-create payload before a build starts."""

import json

import pytest

from tests.factories import ground_object, project_payload, walker_shell


def _create(client, payload):
    return client.post("/api/project/create", json=payload)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.update(ground_objects_properties_json=json.dumps(["not-a-dict"])),
        lambda p: p.update(walker_shells_json=json.dumps([42])),
        lambda p: p.update(walker_shells_json=json.dumps([])),
        lambda p: p.update(ground_objects_properties_json=json.dumps([])),
    ],
)
def test_create_rejects_malformed_nested_payloads(client, mutate) -> None:
    """Bad element shapes are a 422 before a background thread starts."""
    payload = project_payload("BadShape")
    mutate(payload)

    response = _create(client, payload)

    assert response.status_code == 422
    assert response.json()["ok"] is False
    assert client.get("/api/project/status").json()["state"] == "idle"


def test_create_rejects_missing_shell_keys(client) -> None:
    """A shell object without the field set the form promises is rejected."""
    shell = walker_shell()
    del shell["constellation_property"]
    payload = project_payload("MissingShell")
    payload["walker_shells_json"] = json.dumps([shell])

    response = _create(client, payload)

    assert response.status_code == 422
    assert "constellation_property" in response.json()["error"]


def test_create_rejects_comma_station_names(client) -> None:
    """Station names the core CSV parser cannot represent fail at the API edge."""
    ground = ground_object()
    ground["stations"][0]["name"] = "Berlin, DE"
    payload = project_payload("CommaStation")
    payload["ground_objects_properties_json"] = json.dumps([ground])

    response = _create(client, payload)

    assert response.status_code == 422
    assert "commas or newlines" in response.json()["error"]


def test_create_rejects_ground_without_stations_or_data_file(client) -> None:
    """A ground object must carry stations or a data file."""
    payload = project_payload("NoGroundData")
    ground = ground_object()
    del ground["stations"]
    payload["ground_objects_properties_json"] = json.dumps([ground])

    response = _create(client, payload)

    assert response.status_code == 422
    assert "no stations or data_file" in response.json()["error"]
