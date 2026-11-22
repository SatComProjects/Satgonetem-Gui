"""API characterization tests for the diagnostic forwarding path."""

import pytest

pytestmark = pytest.mark.integration


def test_path_between_a_ground_station_and_a_satellite(project_client) -> None:
    """The routing graph exposes a hop-by-hop path with distance and delay."""
    response = project_client.get("/api/routing/path?src=Gnd100&dst=Sat42")

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ok"] is True
    assert data["src"] == "Gnd100"
    assert data["dst"] == "Sat42"
    assert data["found"] is True
    assert data["path_source"] == "routing_graph"
    assert "not the live forwarding table" in data["note"]
    assert data["node_count"] == len(data["hops"]) + 1
    assert data["hops"][0]["source"] == "Gnd100"
    assert data["hops"][-1]["target"] == "Sat42"
    assert data["hops"][0]["type"] == "GroundStationLink"
    assert any(hop["type"] == "InterSatelliteLink" for hop in data["hops"])
    assert data["total_distance_km"] > 0
    assert data["total_delay_ms"] > 0
    assert data["routing_method"] == "static"
    assert data["routing_initiated"] is False
    assert isinstance(data["preference"], str)
    assert data["hops"][0]["delay_ms"] == pytest.approx(
        data["hops"][0]["distance_km"] / 299.792458,
        rel=0.01,
    )


def test_path_rejects_the_same_endpoint(project_client) -> None:
    """A path needs two different endpoints."""
    response = project_client.get("/api/routing/path?src=Sat0&dst=Sat0")

    assert response.status_code == 422
    assert "different" in response.json()["error"].lower()


@pytest.mark.parametrize(
    ("src", "dst"),
    [
        ("Missing", "Sat0"),
        ("Sat0", "Missing"),
        ("Gnd", "Sat0"),
        ("Sat0", "Gndabc"),
    ],
)
def test_path_rejects_malformed_or_unknown_nodes(project_client, src: str, dst: str) -> None:
    """Names outside the Sat/Gnd grammar and missing nodes are 404s."""
    response = project_client.get(f"/api/routing/path?src={src}&dst={dst}")

    assert response.status_code == 404
