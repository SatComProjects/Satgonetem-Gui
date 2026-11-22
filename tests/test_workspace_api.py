"""API characterization tests for the project workspace/catalog."""

import pytest

pytestmark = pytest.mark.integration


def test_workspace_is_empty_initially(client) -> None:
    """No project files are listed before anything is saved to the workspace."""
    response = client.get("/api/projects")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "projects": [], "warnings": []}


def test_save_list_load_duplicate_and_delete(project_client) -> None:
    """A project can be saved, reopened, copied, and deleted by opaque id."""
    saved = project_client.post("/api/project/save-to", json={"name": "WorkspaceDemo"})
    assert saved.status_code == 200, saved.text
    first = saved.json()
    assert first["id"]
    assert first["filename"].endswith(".json")
    assert first["overwritten"] is False

    listing = project_client.get("/api/projects").json()
    assert listing["ok"] is True
    assert listing["warnings"] == []
    assert len(listing["projects"]) == 1
    summary = listing["projects"][0]
    assert summary["id"] == first["id"]
    assert summary["satellites"] == 100
    assert summary["ground_stations"] == 1
    assert summary["shells"] == 1
    assert summary["valid"] is True

    loaded = project_client.post(f"/api/projects/{first['id']}/load")
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()["name"] == "Phase0Constellation"

    in_place = project_client.post("/api/project/save-in-place")
    assert in_place.status_code == 200, in_place.text

    copied = project_client.post(
        f"/api/projects/{first['id']}/duplicate",
        json={"name": "WorkspaceCopy"},
    )
    assert copied.status_code == 200, copied.text
    second = copied.json()
    assert second["id"] != first["id"]

    listing = project_client.get("/api/projects").json()
    assert len(listing["projects"]) == 2

    deleted = project_client.request("DELETE", f"/api/projects/{second['id']}")
    assert deleted.status_code == 200

    current = project_client.request("DELETE", f"/api/projects/{first['id']}")
    assert current.status_code == 409


def test_save_to_rejects_a_collision_without_overwrite(project_client) -> None:
    """A same-name save does not silently overwrite an existing project."""
    assert (
        project_client.post("/api/project/save-to", json={"name": "Collision"}).status_code == 200
    )

    blocked = project_client.post("/api/project/save-to", json={"name": "Collision"})
    assert blocked.status_code == 409

    overwritten = project_client.post(
        "/api/project/save-to", json={"name": "Collision", "overwrite": True}
    )
    assert overwritten.status_code == 200, overwritten.text


def test_save_to_requires_a_loaded_project(client) -> None:
    """There is nothing to serialize before a project is loaded."""
    response = client.post("/api/project/save-to", json={"name": "Nothing"})

    assert response.status_code == 404


def test_save_in_place_requires_a_workspace_file(project_client) -> None:
    """A project created with no save target cannot be saved in place."""
    response = project_client.post("/api/project/save-in-place")

    assert response.status_code == 409
    assert "workspace" in response.json()["error"].lower()


@pytest.mark.parametrize(
    "project_id",
    ["not-an-id", "0000000000000000", "../../etc", "..%2F..%2Fetc"],
)
def test_workspace_uses_opaque_ids(project_client, project_id: str) -> None:
    """Client-supplied paths are never treated as project locations."""
    response = project_client.post(f"/api/projects/{project_id}/load")

    assert response.status_code in {404, 422}
    assert "/etc" not in response.text


def test_workspace_skips_malformed_project_files(project_client, settings) -> None:
    """Unreadable JSON is reported as a warning, not a 500."""
    root = settings.save_root
    root.mkdir(parents=True, exist_ok=True)
    (root / "broken.json").write_text("{not json", encoding="utf-8")

    response = project_client.get("/api/projects")

    assert response.status_code == 200
    data = response.json()
    assert data["projects"] == []
    assert data["warnings"]
    assert any("broken.json" in warning for warning in data["warnings"])
