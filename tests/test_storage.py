"""Tests for path resolution and save-root containment."""

from pathlib import Path

import pytest

from satgonetem_gui.storage import (
    SavePathError,
    resolve_data_file,
    resolve_save_path,
)


def test_resolve_data_file_accepts_absolute_and_relative_paths(tmp_path: Path) -> None:
    """Absolute paths win; relative paths resolve under the search directory."""
    absolute = tmp_path / "absolute.txt"
    absolute.write_text("0,Berlin,52.52,13.405,0.034\n", encoding="utf-8")
    (tmp_path / "relative.txt").write_text("1,Paris,48.8566,2.3522,0.035\n", encoding="utf-8")

    assert resolve_data_file(str(absolute), tmp_path) == absolute
    assert resolve_data_file("relative.txt", tmp_path) == tmp_path / "relative.txt"


def test_resolve_save_path_accepts_a_file_inside_the_root(tmp_path: Path) -> None:
    """A save file under the configured root is allowed."""
    root = tmp_path / "projects"
    root.mkdir()

    path = resolve_save_path(str(root / "constellation.json"), "Constellation", root)

    assert path == root / "constellation.json"


def test_resolve_save_path_appends_safe_name_for_a_directory(tmp_path: Path) -> None:
    """A directory target receives a sanitized project filename."""
    root = tmp_path / "projects"
    root.mkdir()

    path = resolve_save_path(str(root), "My Project/One", root)

    assert path == root / "My_Project_One.json"


def test_resolve_save_path_rejects_paths_outside_the_root(tmp_path: Path) -> None:
    """Traversal and absolute paths outside the save root are rejected."""
    root = tmp_path / "projects"
    root.mkdir()

    with pytest.raises(SavePathError):
        resolve_save_path(str(tmp_path / "outside.json"), "Constellation", root)
    with pytest.raises(SavePathError):
        resolve_save_path("../outside.json", "Constellation", root)


def test_resolve_save_path_returns_none_for_empty_input(tmp_path: Path) -> None:
    """An empty save path means in-memory only."""
    assert resolve_save_path("", "Constellation", tmp_path) is None


def test_resolve_save_path_treats_a_new_directory_name_as_a_directory(tmp_path: Path) -> None:
    """A suffixless target that does not exist yet becomes a project directory."""
    root = tmp_path / "projects"
    root.mkdir()

    path = resolve_save_path(str(root / "new-shell"), "My Project", root)

    assert path == root / "new-shell" / "My_Project.json"
