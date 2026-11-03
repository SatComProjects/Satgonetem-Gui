"""Contract checks for the generated OpenAPI schema."""

import pytest


def test_every_api_route_declares_a_json_success_schema(client) -> None:
    """All JSON routes expose a response schema in the OpenAPI document."""
    paths = client.get("/openapi.json").json()["paths"]
    api_paths = {path: ops for path, ops in paths.items() if path.startswith("/api/")}

    assert api_paths
    for path, operations in api_paths.items():
        for method, operation in operations.items():
            if method not in {"get", "post"}:
                continue
            responses = operation.get("responses", {})
            assert "200" in responses, f"{method.upper()} {path} has no 200 response"
            content = responses["200"].get("content", {})
            if path == "/api/security/captures/{capture_id}":
                assert "application/vnd.tcpdump.pcap" in content
                continue
            assert "application/json" in content, f"{method.upper()} {path} is not JSON"
            assert content["application/json"].get("schema"), (
                f"{method.upper()} {path} has no response schema"
            )


@pytest.mark.parametrize(
    "path",
    [
        "/api/project/create",
        "/api/project/load",
        "/api/routing/apply",
        "/api/traffic/iperf3",
        "/api/traffic/ping",
        "/api/traffic/hping3",
        "/api/traffic/cancel",
        "/api/security/captures",
    ],
)
def test_post_routes_declare_request_schemas(client, path: str) -> None:
    """POST endpoints document their request body schema."""
    paths = client.get("/openapi.json").json()["paths"]
    operation = paths[path]["post"]

    assert "requestBody" in operation
    schema = operation["requestBody"]["content"]["application/json"]["schema"]
    assert schema
