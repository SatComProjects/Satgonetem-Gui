"""Security regression tests for uploaded project documents."""

import json
import tempfile
from pathlib import Path

import pytest


def _post_load(client, document: object):
    return client.post(
        "/api/project/load",
        json={"content": json.dumps(document)},
    )


def test_project_load_rejects_non_object_documents(client) -> None:
    """A JSON array is not an uploaded saved project."""
    response = _post_load(client, ["not", "a", "project"])

    assert response.status_code == 400
    assert "JSON object" in response.json()["error"]


@pytest.mark.parametrize("basename", ["absolute", "traversal"])
def test_project_load_rejects_unsafe_ground_file_basenames(
    client,
    tmp_path: Path,
    basename: str,
) -> None:
    """Absolute and traversal basenames are rejected before any write."""
    target = tmp_path / "sgnt-pwned.txt"
    unsafe_name = str(target) if basename == "absolute" else f"../../{target.name}"
    document = {
        "simulation_property": {"ground_objects_properties": []},
        "ground_files": {
            "original-path": {
                "basename": unsafe_name,
                "content": "0,Berlin,52.52,13.405,0.034\n",
            }
        },
    }
    restore_dirs_before = set(Path(tempfile.gettempdir()).glob("*_ground_files_*"))

    response = _post_load(client, document)

    restore_dirs_after = set(Path(tempfile.gettempdir()).glob("*_ground_files_*"))
    assert response.status_code == 400
    assert "basename" in response.json()["error"]
    assert not target.exists()
    assert restore_dirs_after == restore_dirs_before


@pytest.mark.parametrize("basename", ["../secret.csv", "a/b.csv", "a\\b.csv", "x\x00.csv"])
def test_project_load_rejects_other_traversal_forms(
    client,
    basename: str,
) -> None:
    """Separators, parent components, and NUL bytes never reach the core."""
    document = {
        "simulation_property": {},
        "ground_files": {
            "original-path": {
                "basename": basename,
                "content": "0,Berlin,52.52,13.405,0.034\n",
            }
        },
    }

    response = _post_load(client, document)

    assert response.status_code == 400


def test_project_load_requires_string_ground_file_content(client) -> None:
    """Embedded file content must be text, not an arbitrary JSON value."""
    document = {
        "simulation_property": {},
        "ground_files": {"original-path": {"basename": "stations.csv", "content": ["not", "text"]}},
    }

    response = _post_load(client, document)

    assert response.status_code == 400
    assert "content must be a string" in response.json()["error"]


def test_project_load_rejects_malformed_embedded_station_rows(client) -> None:
    """Embedded files must satisfy the core's five-column parser."""
    document = {
        "simulation_property": {},
        "ground_files": {
            "original-path": {
                "basename": "stations.csv",
                "content": '0,"Berlin, DE",52.52,13.405,0.034\n',
            }
        },
    }

    response = _post_load(client, document)

    assert response.status_code == 400
    assert "five comma-separated columns" in response.json()["error"]


def test_project_load_rejects_duplicate_ground_file_basenames(client) -> None:
    """Two embedded files cannot restore to the same basename."""
    document = {
        "simulation_property": {},
        "ground_files": {
            "first": {
                "basename": "stations.csv",
                "content": "0,Berlin,52.52,13.405,0.034\n",
            },
            "second": {
                "basename": "stations.csv",
                "content": "0,Paris,48.8566,2.3522,0.035\n",
            },
        },
    }

    response = _post_load(client, document)

    assert response.status_code == 400
    assert "unique" in response.json()["error"]


def test_project_load_rejects_non_regular_data_file(client, settings) -> None:
    """A directory inside the save root is not a readable station file."""
    settings.save_root.mkdir(parents=True, exist_ok=True)
    directory = settings.save_root / "stations"
    directory.mkdir()
    document = {
        "simulation_property": {"ground_objects_properties": [{"data_file": str(directory)}]}
    }

    response = _post_load(client, document)

    assert response.status_code == 400
    assert "outside the allowed directories" in response.json()["error"]


def test_project_load_rejects_relative_data_files(client) -> None:
    """Relative paths would be read from the process CWD, not the checked root."""
    document = {
        "simulation_property": {"ground_objects_properties": [{"data_file": "stations.csv"}]}
    }

    response = _post_load(client, document)

    assert response.status_code == 400
    assert "must be absolute" in response.json()["error"]


def test_project_load_rejects_data_file_outside_allowed_roots(
    client,
    tmp_path: Path,
) -> None:
    """A referenced data file outside the packaged and save roots is rejected."""
    outside = tmp_path / "outside-stations.csv"
    outside.write_text("0,Oslo,59.91,10.75,0.01\n", encoding="utf-8")
    document = {"simulation_property": {"ground_objects_properties": [{"data_file": str(outside)}]}}

    response = _post_load(client, document)

    assert response.status_code == 400
    assert "outside the allowed directories" in response.json()["error"]


def test_failed_core_load_removes_restored_ground_files(client) -> None:
    """A core failure after restore does not leave temporary directories behind."""
    document = {
        "network_config": {},
        "simulation_property": {
            "ground_objects_properties": [
                {
                    "identifier": "Ground Stations",
                    "type": "ground_station",
                    "data_file": "missing.csv",
                }
            ]
        },
        "ground_files": {
            "original-path": {
                "basename": "stations.csv",
                "content": "0,Berlin,52.52,13.405,0.034\n",
            }
        },
    }
    restore_dirs_before = set(Path(tempfile.gettempdir()).glob("*_ground_files_*"))

    response = _post_load(client, document)

    restore_dirs_after = set(Path(tempfile.gettempdir()).glob("*_ground_files_*"))
    assert response.status_code == 400
    assert restore_dirs_after == restore_dirs_before
