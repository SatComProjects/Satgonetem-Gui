"""Filesystem path resolution and save-root policy."""

import re
from collections.abc import Iterable
from pathlib import Path


class SavePathError(ValueError):
    """Raised when a requested path escapes the configured roots."""


def resolve_data_file(
    data_file: str,
    search_dir: Path,
    allowed_roots: Iterable[Path] | None = None,
) -> Path:
    """Resolve a contained ground-station data file path.

    Relative paths are tried under ``search_dir`` and under each allowed root.
    Any candidate path must stay inside those roots, and the final path must be
    a regular file.

    Args:
        data_file: Absolute path or path relative to a root.
        search_dir: Directory used to resolve relative paths and an implicit
            allowed root.
        allowed_roots: Additional directories where data files may live.

    Returns:
        Resolved path to an existing regular file.

    Raises:
        SavePathError: If the path escapes every allowed root.
        FileNotFoundError: If the contained path is not a regular file.
    """
    if not isinstance(data_file, str) or not data_file.strip():
        raise FileNotFoundError(f"Ground station data file not found: {data_file!r}")
    if "\x00" in data_file:
        raise SavePathError("Ground station data file path is invalid.")

    search_root = Path(search_dir).expanduser().resolve()
    roots = [search_root]
    if allowed_roots is not None:
        roots.extend(Path(root).expanduser().resolve() for root in allowed_roots)

    path = Path(data_file).expanduser()
    if path.is_absolute():
        candidates = [path]
    else:
        candidates = [search_root / path]
        candidates.extend(root / path for root in roots[1:])

    contained_but_missing = False
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except (OSError, RuntimeError):
            continue
        if not any(_is_within(resolved, root) for root in roots):
            continue
        contained_but_missing = True
        if resolved.is_file():
            return resolved

    if contained_but_missing:
        raise FileNotFoundError(
            f"Ground station data file not found: {data_file!r}"
        )
    raise SavePathError(
        "Ground station data file must be inside an allowed directory: "
        f"{data_file!r}"
    )


def _is_within(path: Path, root: Path) -> bool:
    """Return whether path is at or below root."""
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def safe_project_filename(project_name: str) -> str:
    """Convert a project name into a safe single path component."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", project_name).strip("._-")
    return cleaned or "project"


def resolve_save_path(
    requested: str,
    project_name: str,
    save_root: Path,
) -> Path | None:
    """Resolve a user-supplied save path under the configured root.

    Args:
        requested: Empty string, a directory, or a file path from the form.
        project_name: Name used when the requested path is a directory.
        save_root: Only paths at or below this directory are allowed.

    Returns:
        A concrete file path, or None when the form left the path empty.

    Raises:
        SavePathError: If the requested path escapes the save root.
    """
    if not requested.strip():
        return None

    root = Path(save_root).expanduser().resolve()
    candidate = Path(requested).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        candidate = candidate.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise SavePathError("Save path is invalid.") from exc
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise SavePathError(f"Save path must be inside {root}") from exc

    if candidate.is_dir() or candidate.suffix == "":
        candidate = candidate / f"{safe_project_filename(project_name)}.json"
    return candidate
