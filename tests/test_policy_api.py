"""API behavior for the firewall/QoS policy routes."""

from fastapi.testclient import TestClient

from satgonetem_gui.app import create_app


def _policy() -> dict:
    return {
        "node": "Gnd24",
        "preset": "ddos-mitigation",
        "default_inbound": "accept",
        "allow_established": True,
        "rate_limits": [
            {
                "protocol": "udp",
                "port": 5201,
                "source_cidr": "192.0.2.0/24",
                "packets_per_second": 100,
                "burst": 200,
            }
        ],
    }


def test_policy_list_is_empty_without_project(client) -> None:
    """The applied-policy list is safe to poll before a project is loaded."""
    response = client.get("/api/security/policies")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "nodes": []}


def test_policy_preview_requires_a_project(client) -> None:
    """Preview is project-dependent."""
    response = client.post("/api/security/policies/preview", json=_policy())

    assert response.status_code == 404


def test_policy_apply_requires_a_project(client) -> None:
    """Applying a policy requires a loaded topology."""
    response = client.post("/api/security/policies", json=_policy())

    assert response.status_code == 404


def test_policy_status_requires_a_project(client) -> None:
    """Status reads the node's chain, so it needs a node."""
    response = client.get("/api/security/policies/Gnd24")

    assert response.status_code == 404


def test_policy_clear_requires_a_project(client) -> None:
    """Clearing a policy needs a loaded topology."""
    response = client.post("/api/security/policies/Gnd24/clear")

    assert response.status_code == 404


def test_policy_rejects_cross_family_cidr(client) -> None:
    """A policy family and its CIDRs must match."""
    payload = _policy()
    payload["family"] = "ipv6"

    response = client.post("/api/security/policies/preview", json=payload)

    assert response.status_code == 422
    assert response.json()["ok"] is False


def test_policy_rejects_invalid_port(client) -> None:
    """Ports are validated before any node command is built."""
    payload = _policy()
    payload["rate_limits"][0]["port"] = 70000

    response = client.post("/api/security/policies/preview", json=payload)

    assert response.status_code == 422


def test_policy_page_has_a_policy_unit(settings) -> None:
    """The security page exposes the policy editor."""
    with TestClient(create_app(settings=settings)) as client:
        response = client.get("/security")

    assert response.status_code == 200
    assert "Policy" in response.text
    assert "Preview plan" in response.text
