"""Unit tests for the project workspace/catalog service."""

import asyncio
import json
from datetime import datetime
from pathlib import Path

import pytest

from satgonetem_gui.config import Settings
from satgonetem_gui.errors import APIError
from satgonetem_gui.services.project_catalog_service import ProjectCatalogService
from satgonetem_gui.state import RuntimeState
from satgonetem_gui.storage import (
    workspace_filename,
    workspace_project_id,
    workspace_relative,
)


class FakeProject:
    """Record project loads instead of building a real topology."""

    def __init__(self, name: str = "LoadedProject") -> None:
        self.name = name
        self.calls: list[tuple[str, str]] = []

    async def load(self, content: str, save_path: str = "") -> str:
        self.calls.append((content, save_path))
        return self.name


class FakeGateway:
    """Return configured serialized content without touching the core."""

    def __init__(self, content: str = '{"saved": true}') -> None:
        self.content = content
        self.calls = 0

    def save(self, topology) -> str:
        self.calls += 1
        return self.content


def _document(
    name: str = "Demo",
    *,
    planes: int = 2,
    satellites_per_plane: int = 5,
    shells: int = 1,
    stations: int = 1,
) -> dict:
    """Build the subset of a saved project document the catalog summarizes."""
    return {
        "simulation_property": {
            "simulation_name": name,
            "walker_shells": [
                {
                    "constellation_property": {
                        "amount_of_orbit_plane": planes,
                        "amount_of_satellite_per_orbit_plane": satellites_per_plane,
                    }
                }
                for _ in range(shells)
            ],
            "ground_objects_properties": [
                {
                    "stations": [
                        {
                            "index": index,
                            "name": f"Station{index}",
                            "latitude": 0.0,
                            "longitude": 0.0,
                            "elevation_m": 0.0,
                        }
                        for index in range(stations)
                    ]
                }
            ],
        }
    }


def _catalog(
    settings: Settings,
    *,
    loaded: bool = False,
    save_path: str = "",
    content: str = '{"saved": true}',
) -> tuple[ProjectCatalogService, RuntimeState, FakeProject, FakeGateway]:
    """Build a catalog service with a fake project service and gateway."""
    runtime = RuntimeState()
    if loaded:
        runtime.project.succeed(object(), "LoadedProject", save_path)
    project = FakeProject()
    gateway = FakeGateway(content)
    catalog = ProjectCatalogService(runtime, project, gateway, settings)
    return catalog, runtime, project, gateway


def _write_project(root: Path, relative: str, document: dict) -> Path:
    """Write one workspace project file and return its resolved path."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path.resolve()


def test_catalog_lists_an_empty_workspace(settings) -> None:
    """A missing save root is an empty catalog without warnings."""
    catalog, _, _, _ = _catalog(settings)

    assert catalog.list_projects() == {
        "ok": True,
        "projects": [],
        "warnings": [],
    }


def test_catalog_summarizes_a_project_file(settings) -> None:
    """Summaries expose the project name, counts, and opaque identity."""
    path = _write_project(
        settings.save_root,
        "nested/Demo.json",
        _document("Demo", planes=3, satellites_per_plane=4, shells=2, stations=2),
    )
    catalog, _, _, _ = _catalog(settings)

    listing = catalog.list_projects()

    assert listing["ok"] is True
    assert listing["warnings"] == []
    assert len(listing["projects"]) == 1
    summary = listing["projects"][0]
    assert summary["id"] == workspace_project_id("nested/Demo.json")
    assert summary["name"] == "Demo"
    assert summary["filename"] == "Demo.json"
    assert summary["size_bytes"] == path.stat().st_size
    assert summary["satellites"] == 2 * 3 * 4
    assert summary["ground_stations"] == 2
    assert summary["shells"] == 2
    assert summary["valid"] is True
    assert datetime.fromisoformat(summary["modified_at"]).tzinfo is not None
    assert str(settings.save_root) not in json.dumps(summary)


def test_catalog_counts_stations_embedded_in_the_ground_file(settings) -> None:
    """A data-file-only ground object is counted from the embedded file."""
    document = _document(stations=0)
    document["simulation_property"]["ground_objects_properties"] = [
        {"data_file": "/old/machine/stations.csv"}
    ]
    document["ground_files"] = {
        "/old/machine/stations.csv": {
            "content": "0,Oslo,59.91,10.75,0.01\n1,Rome,41.9,12.5,0.02\n",
            "basename": "stations.csv",
        }
    }
    _write_project(settings.save_root, "Stations.json", document)
    catalog, _, _, _ = _catalog(settings)

    summary = catalog.list_projects()["projects"][0]

    assert summary["ground_stations"] == 2
    assert summary["valid"] is True


def test_catalog_treats_an_unreadable_ground_file_as_zero(settings) -> None:
    """An unavailable data file leaves the count at zero and the project valid."""
    document = _document(stations=0)
    document["simulation_property"]["ground_objects_properties"] = [
        {"data_file": "/missing/stations.csv"}
    ]
    _write_project(settings.save_root, "Missing.json", document)
    catalog, _, _, _ = _catalog(settings)

    summary = catalog.list_projects()["projects"][0]

    assert summary["ground_stations"] == 0
    assert summary["valid"] is True


def test_catalog_accepts_a_runtime_state_document_without_counts(settings) -> None:
    """A document without simulation_property is valid with null counts."""
    _write_project(settings.save_root, "runtime-state.json", {"network_config": {}})
    catalog, _, _, _ = _catalog(settings)

    summary = catalog.list_projects()["projects"][0]

    assert summary["name"] == "runtime-state"
    assert summary["satellites"] is None
    assert summary["ground_stations"] is None
    assert summary["shells"] is None
    assert summary["valid"] is True


def test_catalog_warns_about_malformed_files_and_keeps_valid_ones(settings) -> None:
    """Malformed JSON is a warning containing the filename, never a failure."""
    settings.save_root.mkdir(parents=True, exist_ok=True)
    (settings.save_root / "broken.json").write_text("{not json", encoding="utf-8")
    _write_project(settings.save_root, "Good.json", _document("Good"))
    catalog, _, _, _ = _catalog(settings)

    listing = catalog.list_projects()

    assert [project["filename"] for project in listing["projects"]] == ["Good.json"]
    assert any("broken.json" in warning for warning in listing["warnings"])


def test_catalog_load_reads_by_id_and_installs_the_save_path(settings) -> None:
    """Loading a workspace project passes its contained path to the service."""
    path = _write_project(settings.save_root, "Demo.json", _document("Demo"))
    content = path.read_text(encoding="utf-8")
    catalog, _, project, _ = _catalog(settings)
    identifier = workspace_project_id(workspace_relative(path, settings.save_root))

    name = asyncio.run(catalog.load_project(identifier))

    assert name == "LoadedProject"
    assert project.calls == [(content, str(path))]


@pytest.mark.parametrize("project_id", ["missing", "0" * 16, "../../etc", "ABCDEF0123456789"])
def test_catalog_load_rejects_unknown_or_unsafe_ids(settings, project_id: str) -> None:
    """Only ids matching the safe file set can be loaded."""
    catalog, _, project, _ = _catalog(settings)

    with pytest.raises(APIError) as error:
        asyncio.run(catalog.load_project(project_id))

    assert error.value.status_code == 404
    assert project.calls == []


def test_catalog_save_to_writes_a_new_workspace_project(settings) -> None:
    """Saving to a name stores serialized content and adopts the new path."""
    catalog, runtime, _, gateway = _catalog(settings, loaded=True)

    result = asyncio.run(catalog.save_current_to("Demo Project"))

    target = settings.save_root / workspace_filename("Demo Project")
    assert target.read_text(encoding="utf-8") == gateway.content
    assert result == {
        "ok": True,
        "id": workspace_project_id(workspace_relative(target, settings.save_root)),
        "name": "Demo Project",
        "filename": target.name,
        "overwritten": False,
    }
    assert runtime.project.save_path == str(target.resolve())
    assert gateway.calls == 1


def test_catalog_save_to_requires_a_loaded_project(settings) -> None:
    """There is nothing to serialize before a project is loaded."""
    catalog, _, _, gateway = _catalog(settings)

    with pytest.raises(APIError) as error:
        asyncio.run(catalog.save_current_to("Nothing"))

    assert error.value.status_code == 404
    assert gateway.calls == 0


def test_catalog_save_to_rejects_blank_names(settings) -> None:
    """A whitespace-only name is a client error."""
    catalog, _, _, gateway = _catalog(settings)

    with pytest.raises(APIError) as error:
        asyncio.run(catalog.save_current_to("   "))

    assert error.value.status_code == 422
    assert gateway.calls == 0


def test_catalog_save_to_collision_requires_overwrite(settings) -> None:
    """An existing target is a conflict unless overwrite is requested."""
    catalog, _, _, gateway = _catalog(settings, loaded=True)
    first = asyncio.run(catalog.save_current_to("Demo"))

    with pytest.raises(APIError) as error:
        asyncio.run(catalog.save_current_to("Demo"))
    assert error.value.status_code == 409
    assert gateway.calls == 1

    gateway.content = '{"saved": "replacement"}'
    second = asyncio.run(catalog.save_current_to("Demo", overwrite=True))

    assert second["overwritten"] is True
    assert second["id"] == first["id"]
    target = settings.save_root / first["filename"]
    assert target.read_text(encoding="utf-8") == '{"saved": "replacement"}'


def test_catalog_save_in_place_requires_a_workspace_path(settings) -> None:
    """A project without a save target cannot be saved in place."""
    catalog, _, _, gateway = _catalog(settings, loaded=True)

    with pytest.raises(APIError) as error:
        asyncio.run(catalog.save_current_in_place())

    assert error.value.status_code == 409
    assert "workspace" in error.value.message.lower()
    assert gateway.calls == 0


def test_catalog_save_in_place_rejects_paths_outside_the_workspace(settings) -> None:
    """A session save path outside the save root is not overwritten."""
    outside = settings.save_root.parent / "outside.json"
    catalog, _, _, gateway = _catalog(
        settings,
        loaded=True,
        save_path=str(outside),
    )

    with pytest.raises(APIError) as error:
        asyncio.run(catalog.save_current_in_place())

    assert error.value.status_code == 409
    assert "workspace" in error.value.message.lower()
    assert gateway.calls == 0


def test_catalog_save_in_place_overwrites_the_workspace_file(settings) -> None:
    """Saving in place atomically replaces the current workspace file."""
    target = settings.save_root / "Current.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("old", encoding="utf-8")
    catalog, _, _, gateway = _catalog(
        settings,
        loaded=True,
        save_path=str(target),
    )

    result = asyncio.run(catalog.save_current_in_place())

    assert target.read_text(encoding="utf-8") == gateway.content
    assert result == {
        "ok": True,
        "id": workspace_project_id("Current.json"),
        "name": "LoadedProject",
        "filename": "Current.json",
        "overwritten": True,
    }


def test_catalog_duplicate_copies_without_loading(settings) -> None:
    """Duplicating writes source content under the new name without a load."""
    source = _write_project(settings.save_root, "Source.json", _document("Source"))
    catalog, _, project, gateway = _catalog(settings)
    identifier = workspace_project_id(workspace_relative(source, settings.save_root))

    result = catalog.duplicate_project(identifier, "Copy")

    target = settings.save_root / "Copy.json"
    assert target.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    assert result["id"] == workspace_project_id("Copy.json")
    assert result["filename"] == "Copy.json"
    assert result["name"] == "Copy"
    assert project.calls == []
    assert gateway.calls == 0


def test_catalog_duplicate_rejects_collisions_and_blank_names(settings) -> None:
    """Duplicates never silently overwrite and require a real name."""
    _write_project(settings.save_root, "Source.json", _document("Source"))
    identifier = workspace_project_id("Source.json")
    catalog, _, _, _ = _catalog(settings)

    with pytest.raises(APIError) as collision:
        catalog.duplicate_project(identifier, "Source")
    assert collision.value.status_code == 409

    with pytest.raises(APIError) as blank:
        catalog.duplicate_project(identifier, "   ")
    assert blank.value.status_code == 422


def test_catalog_duplicate_rejects_an_unknown_source(settings) -> None:
    """A missing source id is a 404."""
    catalog, _, _, _ = _catalog(settings)

    with pytest.raises(APIError) as error:
        catalog.duplicate_project("0" * 16, "Copy")

    assert error.value.status_code == 404


def test_catalog_delete_removes_a_workspace_file(settings) -> None:
    """Deleting by id unlinks the resolved project file."""
    path = _write_project(settings.save_root, "Delete.json", _document("Delete"))
    catalog, _, _, _ = _catalog(settings)

    catalog.delete_project(workspace_project_id("Delete.json"))

    assert not path.exists()


def test_catalog_delete_refuses_the_current_workspace_file(settings) -> None:
    """The loaded project's workspace file cannot be deleted underneath it."""
    path = _write_project(settings.save_root, "Current.json", _document("Current"))
    catalog, _, _, _ = _catalog(
        settings,
        loaded=True,
        save_path=str(path),
    )

    with pytest.raises(APIError) as error:
        catalog.delete_project(workspace_project_id("Current.json"))

    assert error.value.status_code == 409
    assert path.exists()


def test_catalog_delete_rejects_an_unknown_id(settings) -> None:
    """An id outside the workspace is a 404."""
    catalog, _, _, _ = _catalog(settings)

    with pytest.raises(APIError) as error:
        catalog.delete_project("0" * 16)

    assert error.value.status_code == 404
