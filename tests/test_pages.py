"""Page-route characterization tests."""

import pytest


@pytest.mark.parametrize(
    ("path", "marker"),
    [
        ("/", "Dashboard"),
        ("/new_project", "Create New Project"),
        ("/ground_stations", "Select Ground Stations"),
        ("/world", "World View"),
        ("/nodes", "Nodes"),
        ("/traffic", "Traffic Generator"),
    ],
)
def test_page_routes_render(client, path: str, marker: str) -> None:
    """Every HTML page returns a rendered template."""
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert marker in response.text


def test_api_documentation_is_available(client) -> None:
    """FastAPI serves its interactive documentation."""
    response = client.get("/docs")

    assert response.status_code == 200
    assert "swagger" in response.text.lower()


def test_openapi_schema_contains_all_public_routes(client) -> None:
    """The generated schema includes the routes the frontend depends on."""
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    expected = {
        "/api/status",
        "/api/project/create",
        "/api/project/exists",
        "/api/project/config",
        "/api/project/load",
        "/api/project/save",
        "/api/satellites",
        "/api/ground_stations",
        "/api/links",
        "/api/nodes",
        "/api/nodes/{name}",
        "/api/routing/status",
        "/api/routing/apply",
        "/api/routing/delete",
        "/api/gonetem/start",
        "/api/gonetem/stop",
        "/api/traffic/nodes",
        "/api/traffic/iperf3",
        "/api/traffic/ping",
        "/api/traffic/hping3",
        "/api/traffic/status",
        "/api/traffic/cancel",
    }
    assert expected.issubset(paths)
