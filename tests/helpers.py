"""Shared helpers for API-level tests."""

import time


def wait_for_project_state(client, states: set[str], timeout: float = 5.0) -> dict:
    """Poll /api/project/status until it reaches one of the requested states."""
    deadline = time.monotonic() + timeout
    last_status = None
    while time.monotonic() < deadline:
        response = client.get("/api/project/status")
        assert response.status_code == 200, response.text
        last_status = response.json()
        if last_status["state"] in states:
            return last_status
        time.sleep(0.02)
    raise AssertionError(f"project did not reach {states}; last status: {last_status}")
