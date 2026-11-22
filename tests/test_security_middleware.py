"""Host and cross-origin protections for the local control panel."""

from fastapi.testclient import TestClient

from satgonetem_gui.app import create_app
from satgonetem_gui.config import Settings


def _make_app(tmp_path, host="127.0.0.1"):
    return create_app(settings=Settings(host=host, port=8000, save_root=tmp_path))


def test_untrusted_host_header_is_rejected(client) -> None:
    """DNS-rebinding requests with a foreign Host header cannot reach the app."""
    response = client.get("/api/status", headers={"Host": "evil.example"})

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert "Host" in response.json()["error"]


def test_cross_origin_mutation_is_rejected(client) -> None:
    """A browser mutation from another origin is blocked before routing."""
    response = client.post(
        "/api/routing/apply",
        headers={"Origin": "https://evil.example"},
        json={"method": "static"},
    )

    assert response.status_code == 403
    assert "Cross-origin" in response.json()["error"]


def test_same_origin_mutation_is_not_rejected_by_the_guard(client) -> None:
    """The normal same-origin browser path still reaches the application."""
    response = client.post(
        "/api/routing/apply",
        headers={"Origin": "http://testserver"},
        json={"method": "static"},
    )

    assert response.status_code == 404


def test_malformed_host_header_returns_a_guard_response(tmp_path) -> None:
    """A malformed IPv6 Host header is rejected instead of raising a 500."""
    app = _make_app(tmp_path)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.get("/api/status", headers={"Host": "[::1"})

    assert response.status_code == 400
    assert response.json()["ok"] is False


def test_malformed_origin_header_returns_a_guard_response(tmp_path) -> None:
    """A malformed IPv6 Origin header is rejected instead of raising a 500."""
    app = _make_app(tmp_path)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.post(
            "/api/routing/apply",
            headers={"Origin": "http://[::1"},
            json={"method": "static"},
        )

    assert response.status_code == 403
    assert "Cross-origin" in response.json()["error"]


def test_configured_host_is_matched_case_insensitively(tmp_path, monkeypatch) -> None:
    """An operator-configured mixed-case host matches lowercased requests."""
    monkeypatch.delenv("SATGONETEM_GUI_ALLOWED_HOSTS", raising=False)
    app = _make_app(tmp_path, host="MyHost.local")
    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.get(
            "/api/status", headers={"Host": "myhost.local"}
        )

    assert response.status_code == 200


def test_wildcard_bind_accepts_local_addresses(tmp_path, monkeypatch) -> None:
    """Binding to 0.0.0.0 accepts the machine's own hostname and addresses."""
    monkeypatch.delenv("SATGONETEM_GUI_ALLOWED_HOSTS", raising=False)
    monkeypatch.setattr("satgonetem_gui.app.socket.gethostname", lambda: "workstation")
    monkeypatch.setattr("satgonetem_gui.app.socket.getfqdn", lambda: "workstation.local")
    monkeypatch.setattr(
        "satgonetem_gui.app.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("192.168.1.5", 0))],
    )
    app = _make_app(tmp_path, host="0.0.0.0")
    with TestClient(app, raise_server_exceptions=False) as test_client:
        by_address = test_client.get(
            "/api/status", headers={"Host": "192.168.1.5:8000"}
        )
        by_name = test_client.get(
            "/api/status", headers={"Host": "workstation.local"}
        )

    assert by_address.status_code == 200
    assert by_name.status_code == 200
