"""Tests for path resolution and save-root containment."""

import os
import re
from pathlib import Path

import pytest

from satgonetem_gui.storage import (
    SavePathError,
    iter_workspace_project_files,
    resolve_data_file,
    resolve_save_path,
    resolve_workspace_project,
    safe_project_filename,
    validate_workspace_target,
    workspace_filename,
    workspace_project_id,
    workspace_relative,
    write_workspace_project,
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


def test_workspace_project_id_is_opaque_and_stable() -> None:
    """Ids are a deterministic 16-hex digest that does not reveal the path."""
    identifier = workspace_project_id("nested/Alpha Project.json")

    assert identifier == workspace_project_id("nested/Alpha Project.json")
    assert re.fullmatch(r"[0-9a-f]{16}", identifier)
    assert identifier != workspace_project_id("nested/Beta.json")
    assert "Alpha" not in identifier


def test_workspace_relative_uses_a_posix_relative_path(tmp_path: Path) -> None:
    """Nested project files report a root-relative POSIX path."""
    root = tmp_path / "projects"
    nested = root / "nested"
    nested.mkdir(parents=True)

    assert workspace_relative(nested / "one.json", root) == "nested/one.json"


def test_workspace_relative_rejects_paths_outside_the_root(tmp_path: Path) -> None:
    """A resolved path outside the root is not a workspace-relative path."""
    root = tmp_path / "projects"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")

    with pytest.raises(SavePathError):
        workspace_relative(outside, root)


def test_workspace_filename_is_safe_and_always_json() -> None:
    """The filename derives from the sanitized project name."""
    filename = workspace_filename("../../My Project")

    assert filename.endswith(".json")
    assert "/" not in filename
    assert ".." not in filename
    assert filename == workspace_filename("../../My Project")


def test_iter_workspace_project_files_filters_and_orders(tmp_path: Path) -> None:
    """Hidden, symlinked, and temporary files are skipped; newest comes first."""
    root = tmp_path / "projects"
    nested = root / "nested"
    nested.mkdir(parents=True)
    (root / ".cache").mkdir()
    old = root / "old.json"
    old.write_text("{}", encoding="utf-8")
    new = nested / "new.json"
    new.write_text("{}", encoding="utf-8")
    (root / ".hidden.json").write_text("{}", encoding="utf-8")
    (root / ".cache" / "cached.json").write_text("{}", encoding="utf-8")
    (root / "draft.json.tmp").write_text("{}", encoding="utf-8")
    (root / "upload.tmp").write_text("{}", encoding="utf-8")
    os.utime(old, (1_000.0, 1_000.0))
    os.utime(new, (2_000.0, 2_000.0))

    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    (root / "linked.json").symlink_to(outside)
    linked_dir = root / "linked-directory"
    linked_dir.symlink_to(tmp_path, target_is_directory=True)
    (tmp_path / "escaped.json").write_text("{}", encoding="utf-8")

    files = iter_workspace_project_files(root)

    assert files == [new.resolve(), old.resolve()]


def test_iter_workspace_project_files_honors_the_limit(tmp_path: Path) -> None:
    """Only the newest files are returned when a limit is provided."""
    root = tmp_path / "projects"
    root.mkdir()
    for index in range(3):
        path = root / f"project-{index}.json"
        path.write_text("{}", encoding="utf-8")
        os.utime(path, (1_000.0 + index, 1_000.0 + index))

    files = iter_workspace_project_files(root, limit=2)

    assert [path.name for path in files] == ["project-2.json", "project-1.json"]
    assert iter_workspace_project_files(root, limit=0) == []


def test_iter_workspace_project_files_handles_a_missing_root(tmp_path: Path) -> None:
    """An absent save root is an empty workspace, not an error."""
    assert iter_workspace_project_files(tmp_path / "missing") == []


def test_resolve_workspace_project_matches_only_safe_ids(tmp_path: Path) -> None:
    """Ids resolve within the safe file set; traversal and junk return None."""
    root = tmp_path / "projects"
    nested = root / "nested"
    nested.mkdir(parents=True)
    target = nested / "Alpha.json"
    target.write_text("{}", encoding="utf-8")
    identifier = workspace_project_id(workspace_relative(target, root))

    assert resolve_workspace_project(root, identifier) == target.resolve()
    assert resolve_workspace_project(root, "0" * 16) is None
    assert resolve_workspace_project(root, "A" * 16) is None
    assert resolve_workspace_project(root, "../../etc") is None
    assert resolve_workspace_project(root, "../" + identifier) is None


def test_validate_workspace_target_keeps_targets_inside_the_root(tmp_path: Path) -> None:
    """Contained JSON targets pass; traversal, outside, and non-JSON fail."""
    root = tmp_path / "projects"
    root.mkdir()
    inside = root / "nested" / "project.json"

    assert validate_workspace_target(inside, root) == inside.resolve()

    with pytest.raises(SavePathError):
        validate_workspace_target(tmp_path / "outside.json", root)
    with pytest.raises(SavePathError):
        validate_workspace_target(root / ".." / "escape.json", root)
    with pytest.raises(SavePathError):
        validate_workspace_target(root / "notes.txt", root)
    with pytest.raises(SavePathError):
        validate_workspace_target(root, root)


def test_validate_workspace_target_rejects_an_escaping_symlink(tmp_path: Path) -> None:
    """A symlink inside the root cannot redirect a write outside it."""
    root = tmp_path / "projects"
    root.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    link = root / "linked.json"
    link.symlink_to(outside)
    inside = root / "inside.json"
    inside.write_text("{}", encoding="utf-8")
    inside_link = root / "inside-link.json"
    inside_link.symlink_to(inside)

    with pytest.raises(SavePathError):
        validate_workspace_target(link, root)
    with pytest.raises(SavePathError):
        validate_workspace_target(inside_link, root)


def test_write_workspace_project_replaces_content_without_leaving_temp_files(
    tmp_path: Path,
) -> None:
    """Writes are atomic and replace existing content."""
    target = tmp_path / "projects" / "project.json"

    write_workspace_project(target, "first")
    write_workspace_project(target, "second")

    assert target.read_text(encoding="utf-8") == "second"
    assert [path.name for path in target.parent.iterdir()] == ["project.json"]
