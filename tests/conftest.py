"""Shared pytest fixtures for the SatGoNetem GUI tests."""

import os
import tempfile

# Matplotlib is imported transitively by satgonetem. Give it a writable cache
# before the application package is imported.
os.environ.setdefault("MPLCONFIGDIR", tempfile.mkdtemp(prefix="satgonetem-mpl-"))

import pytest
from fastapi.testclient import TestClient

from satgonetem_gui.app import create_app
from satgonetem_gui.config import Settings
from tests.helpers import wait_for_project_state


@pytest.fixture()
def settings(tmp_path) -> Settings:
    """Use an isolated save root for every test."""
    return Settings(
        host="127.0.0.1",
        port=8000,
        save_root=tmp_path / "projects",
    )


@pytest.fixture()
def application(settings):
    """Create a fresh FastAPI app with isolated runtime state."""
    return create_app(settings=settings)


@pytest.fixture()
def client(application):
    """Provide a TestClient for one isolated application instance."""
    with TestClient(application, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture()
def services(application):
    """Return the service container attached to the test application."""
    return application.state.services


@pytest.fixture()
def project_client(client):
    """Provide a client with a real 10x10 topology loaded."""
    from tests.factories import project_payload

    response = client.post("/api/project/create", json=project_payload())
    assert response.status_code == 200
    status = wait_for_project_state(client, {"loaded"})
    assert status["loaded"] is True
    return client
