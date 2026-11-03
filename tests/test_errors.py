"""Tests for the common API error envelope."""


def test_unknown_route_uses_the_error_envelope(client) -> None:
    """Framework-level 404s use the same envelope as API errors."""
    response = client.get("/api/does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["ok"] is False
    assert body["error"]


def test_missing_project_uses_the_error_envelope(client) -> None:
    """A known route without a loaded project uses the envelope."""
    response = client.get("/api/satellites")

    assert response.status_code == 404
    assert response.json()["ok"] is False


def test_malformed_json_returns_422(client) -> None:
    """Malformed request bodies are validation errors, not server errors."""
    response = client.post(
        "/api/project/create",
        content="not-json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["ok"] is False
    assert body["error"]
    assert "detail" not in body


def test_missing_required_fields_return_422(client) -> None:
    """Pydantic validates create requests before the endpoint runs."""
    response = client.post("/api/project/create", json={})

    assert response.status_code == 422
    assert response.json()["ok"] is False


def test_invalid_project_file_returns_400(project_client) -> None:
    """A syntactically invalid project upload is a client error."""
    response = project_client.post(
        "/api/project/load",
        json={"content": "{not valid json"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["ok"] is False
    assert body["error"]


def test_known_500_uses_the_envelope(project_client, monkeypatch) -> None:
    """Handled server failures use the same envelope."""
    from satgonetem_gui.state import app_state

    def fail(*_args, **_kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(app_state.topology_manager, "to_file", fail)

    response = project_client.get("/api/project/save")

    assert response.status_code == 500
    assert response.json() == {"ok": False, "error": "Project save failed."}


def test_unexpected_500_uses_the_envelope(client, monkeypatch) -> None:
    """Unhandled exceptions are converted to the common envelope."""
    from satgonetem_gui.state import app_state

    monkeypatch.setattr(
        app_state,
        "get_status_dict",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    response = client.get("/api/status")

    assert response.status_code == 500
    assert response.json() == {"ok": False, "error": "Internal server error."}


def test_malformed_shell_json_returns_422(client) -> None:
    """Embedded form JSON is validated before a background build starts."""
    from tests.factories import project_payload

    payload = project_payload("BadShells")
    payload["walker_shells_json"] = "not-json"

    response = client.post("/api/project/create", json=payload)

    assert response.status_code == 422
    assert response.json()["ok"] is False
