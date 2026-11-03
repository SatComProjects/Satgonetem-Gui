"""Application-factory isolation tests."""

from fastapi.testclient import TestClient

from satgonetem_gui.app import create_app
from satgonetem_gui.config import Settings
from tests.factories import project_payload
from tests.helpers import wait_for_project_state


def _settings(tmp_path, name: str) -> Settings:
    return Settings(
        host="127.0.0.1",
        port=8000,
        save_root=tmp_path / name,
    )


def test_create_app_isolates_runtime_state(tmp_path) -> None:
    """Two app instances do not share services or project state."""
    first = create_app(settings=_settings(tmp_path, "first"))
    second = create_app(settings=_settings(tmp_path, "second"))

    assert first.state.services is not second.state.services
    assert first.state.services.runtime is not second.state.services.runtime

    first.state.services.runtime.project.succeed(object(), "OnlyFirst", "")

    assert first.state.services.runtime.project.loaded is True
    assert second.state.services.runtime.project.loaded is False


def test_http_state_does_not_leak_between_apps(tmp_path) -> None:
    """A project loaded in one app is not visible in another app."""
    first = create_app(settings=_settings(tmp_path, "first"))
    second = create_app(settings=_settings(tmp_path, "second"))

    with TestClient(first) as first_client:
        response = first_client.post(
            "/api/project/create",
            json=project_payload("FirstApp"),
        )
        assert response.status_code == 200
        wait_for_project_state(first_client, {"loaded"})

    with TestClient(second) as second_client:
        status = second_client.get("/api/project/status")
        assert status.status_code == 200
        assert status.json()["state"] == "idle"


def test_global_app_state_singleton_is_gone() -> None:
    """Runtime state is owned by each application, not by a module global."""
    import satgonetem_gui.state as state_module

    assert not hasattr(state_module, "app_state")
