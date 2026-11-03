"""Shared pytest fixtures for the SatGoNetem GUI tests."""

import os
import tempfile

# Matplotlib is imported transitively by satgonetem. Give it a writable cache
# before the application package is imported.
os.environ.setdefault("MPLCONFIGDIR", tempfile.mkdtemp(prefix="satgonetem-mpl-"))

import pytest
from fastapi.testclient import TestClient

from satgonetem_gui.app import app
from satgonetem_gui.state import app_state


def _reset_state() -> None:
    """Restore the process-global app state to its startup values."""
    app_state.topology_manager = None
    app_state.project_name = None
    app_state.creating = False
    with app_state.jobs_lock:
        app_state.jobs.clear()


@pytest.fixture()
def client():
    """Provide a TestClient with a clean global state for each test."""
    _reset_state()
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    _reset_state()


@pytest.fixture()
def project_client(client):
    """Provide a client with a real 10x10 topology loaded."""
    from tests.factories import build_project

    build_project()
    assert app_state.topology_manager is not None, "10x10 project fixture failed to load"
    return client
