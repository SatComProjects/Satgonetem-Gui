"""Tests for path resolution and save-root containment."""

from pathlib import Path

import pytest

from satgonetem_gui.storage import (
    SavePathError,
    resolve_data_file,
    resolve_save_path,
    safe_project_filename,
)


def test_resolve_data_file_accepts_paths_inside_allowed_roots(tmp_path: Path) -> None:
    """Relative paths use the search directory; absolute paths may use a root."""
    search = tmp_path / "presets"
    search.mkdir()
    allowed = tmp_path / "projects"
    allowed.mkdir()
    relative = search / "relative.txt"
    relative.write_text("1,Paris,48.8566,2.3522,0.035\n", encoding="utf-8")
    absolute = allowed / "absolute.txt"
    absolute.write_text("0,Berlin,52.52,13.405,0.034\n", encoding="utf-8")

    assert resolve_data_file("relative.txt", search) == relative.resolve()
    assert resolve_data_file(str(absolute), search, allowed_roots=(allowed,)) == absolute.resolve()
    assert resolve_data_file("absolute.txt", search, allowed_roots=(allowed,)) == absolute.resolve()


def test_resolve_data_file_rejects_paths_outside_allowed_roots(tmp_path: Path) -> None:
    """Absolute paths and traversal outside the roots are rejected."""
    search = tmp_path / "presets"
    search.mkdir()
    allowed = tmp_path / "projects"
    allowed.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("0,Oslo,59.91,10.75,0.01\n", encoding="utf-8")

    with pytest.raises(SavePathError):
        resolve_data_file(str(outside), search, allowed_roots=(allowed,))
    with pytest.raises(SavePathError):
        resolve_data_file("../outside.txt", search, allowed_roots=(allowed,))
    with pytest.raises(SavePathError):
        resolve_data_file(str(outside), search)


def test_resolve_data_file_requires_a_regular_file(tmp_path: Path) -> None:
    """Directories and missing files are not valid data files."""
    search = tmp_path / "presets"
    search.mkdir()
    directory = search / "stations"
    directory.mkdir()

    with pytest.raises(FileNotFoundError):
        resolve_data_file(str(directory), search)
    with pytest.raises(FileNotFoundError):
        resolve_data_file("missing.txt", search)


def test_safe_project_filename_keeps_distinct_names_distinct() -> None:
    """Names that sanitize to the same text still produce different files."""
    names = ["東京", "***", "!!!", "___", "My Project", "my project"]
    filenames = [safe_project_filename(name) for name in names]

    assert len(set(filenames)) == len(names)
    assert all(filenames)


def test_safe_project_filename_does_not_reuse_a_generated_name() -> None:
    """A literal name matching another name's generated filename is hashed."""
    generated = safe_project_filename("My Project")

    assert safe_project_filename(generated) != generated


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

    assert path == root / f"{safe_project_filename('My Project/One')}.json"
    assert path.name.startswith("My_Project_One-")


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

    assert path == root / "new-shell" / f"{safe_project_filename('My Project')}.json"


def test_resolve_save_path_keeps_an_existing_suffixless_file(tmp_path: Path) -> None:
    """An existing file without a suffix is a save target, not a directory."""
    root = tmp_path / "projects"
    root.mkdir()
    target = root / "constellation"
    target.write_text("{}", encoding="utf-8")

    path = resolve_save_path(str(target), "Constellation", root)

    assert path == target
