"""Tests for save-root containment and safe file targets."""

from pathlib import Path

import satgonetem_gui.app as app_module
from tests.factories import project_payload
from tests.helpers import wait_for_project_state


def test_save_path_outside_root_is_rejected(client, monkeypatch, tmp_path: Path) -> None:
    """The create endpoint rejects writes outside the configured save root."""
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setattr(app_module, "SAVE_ROOT", allowed)
    payload = project_payload("Outside", save_path=str(tmp_path / "outside.json"))

    response = client.post("/api/project/create", json=payload)

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert client.get("/api/project/status").json()["state"] == "idle"


def test_save_path_inside_root_writes_the_project(client, monkeypatch, tmp_path: Path) -> None:
    """A target inside the allowed root is written and reported in config."""
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    monkeypatch.setattr(app_module, "SAVE_ROOT", allowed)
    target = allowed / "inside.json"
    payload = project_payload("Inside", save_path=str(target))

    response = client.post("/api/project/create", json=payload)

    assert response.status_code == 200
    status = wait_for_project_state(client, {"loaded"})
    assert status["project_name"] == "Inside"
    assert target.exists()
    config = client.get("/api/project/config?name=Inside").json()
    assert config["save_path"] == str(target)
