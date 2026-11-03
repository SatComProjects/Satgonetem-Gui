"""Characterization tests against a real 10x10 topology."""

import json

import pytest

from tests.factories import PLANES, PROJECT_NAME, SATELLITES_PER_PLANE, project_payload
from tests.helpers import wait_for_project_state

pytestmark = pytest.mark.integration


def _node_named(client, node_type: str) -> dict:
    nodes = client.get("/api/nodes").json()
    return next(node for node in nodes if node["type"] == node_type)


def test_status_reports_10x10_topology(project_client) -> None:
    """The dashboard status reflects the loaded 10x10 constellation."""
    response = project_client.get("/api/status")

    assert response.status_code == 200
    data = response.json()
    assert data["constellation_loaded"] is True
    assert data["satellites"] == PLANES * SATELLITES_PER_PLANE
    assert data["ground_stations"] == 1
    assert data["links"] >= 200
    assert data["gonetem_is_on"] is False


def test_satellites_endpoint(project_client) -> None:
    """Every satellite is returned with a position."""
    response = project_client.get("/api/satellites")

    assert response.status_code == 200
    satellites = response.json()
    assert len(satellites) == PLANES * SATELLITES_PER_PLANE
    assert {"id", "name", "position"} == set(satellites[0])
    assert set(satellites[0]["position"]) == {"latitude", "longitude", "altitude"}


def test_ground_stations_endpoint(project_client) -> None:
    """The Berlin ground station is returned with its city."""
    response = project_client.get("/api/ground_stations")

    assert response.status_code == 200
    stations = response.json()
    assert len(stations) == 1
    assert stations[0]["name"] == "Gnd100"
    assert stations[0]["city"] == "Berlin"


def test_links_endpoint(project_client) -> None:
    """Inter-satellite and ground-station links are both present."""
    response = project_client.get("/api/links")

    assert response.status_code == 200
    links = response.json()
    assert len(links) >= 200
    link_types = {link["type"] for link in links}
    assert "InterSatelliteLink" in link_types
    assert "GroundStationLink" in link_types
    assert all(
        {
            "key",
            "src",
            "dst",
            "type",
            "direction",
            "distance_km",
            "capacity_kbps",
            "delay_ms",
            "state",
        }
        == set(link)
        for link in links
    )
    assert all(link["capacity_kbps"] > 0 for link in links)
    assert all(link["delay_ms"] >= 0 for link in links)


def test_nodes_and_node_detail(project_client) -> None:
    """The node explorer lists all nodes and can expand a satellite and a station."""
    nodes_response = project_client.get("/api/nodes")
    assert nodes_response.status_code == 200
    nodes = nodes_response.json()
    assert len(nodes) == PLANES * SATELLITES_PER_PLANE + 1

    ground_station = _node_named(project_client, "ground_station")
    satellite_response = project_client.get("/api/nodes/Sat0")
    ground_response = project_client.get(f"/api/nodes/{ground_station['name']}")

    assert satellite_response.status_code == 200
    assert satellite_response.json()["node"]["type"] == "satellite"
    assert satellite_response.json()["node"]["interfaces"]
    assert ground_response.status_code == 200
    assert ground_response.json()["node"]["type"] == "ground_station"
    assert ground_response.json()["node"]["city"] == "Berlin"


def test_unknown_node_returns_404(project_client) -> None:
    """A missing node name is a 404, not a server error."""
    response = project_client.get("/api/nodes/NoSuchNode")

    assert response.status_code == 404


def test_project_exists_after_build(project_client) -> None:
    """The create-page poll finds the loaded project by its submitted name."""
    response = project_client.get(f"/api/project/exists?name={PROJECT_NAME}")

    assert response.status_code == 200
    assert response.json() == {"exists": True}


def test_project_status_reports_loaded(project_client) -> None:
    """The lifecycle endpoint exposes the loaded project and its name."""
    response = project_client.get("/api/project/status")

    assert response.status_code == 200
    data = response.json()
    assert data["state"] == "loaded"
    assert data["project_name"] == PROJECT_NAME
    assert data["loaded"] is True
    assert data["error"] is None


def test_routing_status_without_containers(project_client) -> None:
    """Routing is not applied until GoNetem is running."""
    response = project_client.get("/api/routing/status")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["gonetem_is_on"] is False
    assert data["addressing_applied"] is False
    assert data["routing_initiated"] is False
    assert data["routing_method"] == "static"


def test_traffic_nodes(project_client) -> None:
    """Traffic endpoints are addressable nodes that have interfaces."""
    response = project_client.get("/api/traffic/nodes")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["nodes"] == [
        {
            "name": "Gnd100",
            "type": "ground_station",
            "label": "Gnd100 (Berlin)",
        }
    ]


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/traffic/iperf3", {"src": "Sat0", "dst": "Sat1"}),
        ("/api/traffic/ping", {"src": "Sat0", "dst": "Sat1"}),
        ("/api/traffic/hping3", {"src": "Sat0", "dst": "Sat1"}),
    ],
)
def test_traffic_routes_require_gonetem(project_client, path: str, body: dict) -> None:
    """Traffic cannot start before the containers are running."""
    response = project_client.post(path, json=body)

    assert response.status_code == 409


def test_routing_apply_requires_gonetem(project_client) -> None:
    """Routing cannot be applied before the containers are running."""
    response = project_client.post("/api/routing/apply", json={"method": "static"})

    assert response.status_code == 409


def test_gonetem_start_and_stop_with_fake_manager(project_client, services, monkeypatch) -> None:
    """The start/stop routes can be exercised without launching Docker."""
    controller = services.routing.controller
    monkeypatch.setattr(controller, "start_gonetem", lambda _topology: None)
    monkeypatch.setattr(controller, "stop_gonetem", lambda _topology: None)

    start_response = project_client.post("/api/gonetem/start")
    stop_response = project_client.post("/api/gonetem/stop")

    assert start_response.status_code == 200
    assert start_response.json() == {"ok": True}
    assert stop_response.status_code == 200
    assert stop_response.json() == {"ok": True}


def test_project_save_returns_downloadable_json(project_client) -> None:
    """Saving embeds the simulation property and ground-station files."""
    response = project_client.get("/api/project/save")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["filename"] == f"{PROJECT_NAME}.json"
    saved = json.loads(data["content"])
    assert saved["simulation_property"]["simulation_name"] == PROJECT_NAME
    assert saved["ground_files"]


def test_save_load_round_trip_restores_topology(project_client) -> None:
    """Saved content can be loaded back through the API."""
    saved = project_client.get("/api/project/save").json()

    load_response = project_client.post("/api/project/load", json={"content": saved["content"]})

    assert load_response.status_code == 200
    assert load_response.json()["ok"] is True
    status = project_client.get("/api/status").json()
    assert status["satellites"] == PLANES * SATELLITES_PER_PLANE
    assert status["ground_stations"] == 1


def test_load_preserves_user_facing_name(project_client) -> None:
    """Loading a saved project keeps the name the user submitted."""
    saved = project_client.get("/api/project/save").json()

    response = project_client.post("/api/project/load", json={"content": saved["content"]})

    assert response.status_code == 200
    assert response.json()["name"] == PROJECT_NAME
    saved_again = project_client.get("/api/project/save").json()
    assert saved_again["filename"] == f"{PROJECT_NAME}.json"


def test_project_config_returns_editable_fields(project_client) -> None:
    """The edit form can read back the submitted project configuration."""
    response = project_client.get(f"/api/project/config?name={PROJECT_NAME}")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == PROJECT_NAME
    assert data["update_time"] == 5
    assert data["isl_capacity"] == 100000
    assert data["gs_capacity"] == 100000
    assert data["save_path"] == ""
    assert len(data["walker_shells"]) == 1
    grounds = data["ground_objects_properties"]
    assert len(grounds) == 1
    assert len(grounds[0]["stations"]) == 1
    assert grounds[0]["stations"][0]["name"] == "Berlin"


def test_config_returns_preserved_save_path(client, settings) -> None:
    """The session keeps the save path entered on the create form."""
    payload = project_payload("WithPath", save_path=str(settings.save_root))

    create_response = client.post("/api/project/create", json=payload)
    assert create_response.status_code == 200
    wait_for_project_state(client, {"loaded"})
    response = client.get("/api/project/config?name=WithPath")

    assert response.status_code == 200
    assert response.json()["save_path"] == str(settings.save_root)


def test_edit_round_trip_preserves_ground_stations(project_client) -> None:
    """The config payload can be submitted back through the create form."""
    config = project_client.get(f"/api/project/config?name={PROJECT_NAME}").json()
    payload = project_payload("Phase1Edited")
    payload["update_time"] = str(config["update_time"])
    payload["isl_capacity"] = str(config["isl_capacity"])
    payload["gs_capacity"] = str(config["gs_capacity"])
    payload["save_path"] = config["save_path"]
    payload["walker_shells_json"] = json.dumps(config["walker_shells"])
    payload["ground_objects_properties_json"] = json.dumps(config["ground_objects_properties"])

    response = project_client.post("/api/project/create", json=payload)

    assert response.status_code == 200
    status = wait_for_project_state(project_client, {"loaded"})
    assert status["project_name"] == "Phase1Edited"
    stations = project_client.get("/api/ground_stations").json()
    assert len(stations) == 1
    assert stations[0]["city"] == "Berlin"


def test_invalid_iperf3_numeric_payload_returns_422(project_client) -> None:
    """Invalid numbers are rejected by the request schema before the handler."""
    response = project_client.post(
        "/api/traffic/iperf3",
        json={"src": "Sat0", "dst": "Sat1", "duration": "not-a-number"},
    )

    assert response.status_code == 422


def test_payload_factory_uses_10x10() -> None:
    """The project fixture is the agreed 10x10 topology, not a 3x3 smoke grid."""
    shells = json.loads(project_payload()["walker_shells_json"])
    properties = shells[0]["constellation_property"]

    assert properties["amount_of_orbit_plane"] == 10
    assert properties["amount_of_satellite_per_orbit_plane"] == 10


def test_cancel_api_stops_a_fake_job(project_client, services) -> None:
    """The cancel endpoint stops the flow and reports a terminal status."""

    class FakeFlow:
        def __init__(self) -> None:
            self.stopped = False

        def stop(self) -> None:
            self.stopped = True

    flow = FakeFlow()
    job = services.traffic.jobs.create("ping", flow, "Sat0", "Sat1")

    cancel = project_client.post(
        "/api/traffic/cancel",
        json={"job_id": job.job_id},
    )
    status = project_client.get(f"/api/traffic/status?job_id={job.job_id}")

    assert cancel.status_code == 200
    assert flow.stopped is True
    assert status.status_code == 200
    assert status.json()["status"] == "cancelled"


def test_cancel_api_rejects_a_finished_job(project_client, services) -> None:
    """Cancelling a terminal job returns 409 with the error envelope."""
    job = services.traffic.jobs.create("ping", object(), "Sat0", "Sat1")
    job.transition("done")

    response = project_client.post(
        "/api/traffic/cancel",
        json={"job_id": job.job_id},
    )

    assert response.status_code == 409
    assert response.json()["ok"] is False


def test_stop_clears_addressing_without_unloading_project(
    project_client, services, monkeypatch
) -> None:
    """Stopping containers clears address state but keeps the project loaded."""
    services.topology.set_addressing_applied(True)
    monkeypatch.setattr(services.routing.controller, "stop_gonetem", lambda _topology: None)

    response = project_client.post("/api/gonetem/stop")
    routing = project_client.get("/api/routing/status").json()

    assert response.status_code == 200
    assert routing["addressing_applied"] is False
    assert services.topology.status()["constellation_loaded"] is True
