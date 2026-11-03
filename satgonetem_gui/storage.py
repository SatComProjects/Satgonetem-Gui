"""Filesystem path resolution and save-root policy."""

import re
from pathlib import Path


class SavePathError(ValueError):
    """Raised when a requested save path escapes the configured root."""


def resolve_data_file(data_file: str, search_dir: Path) -> Path:
    """Resolve a ground-station data file path.

    Args:
        data_file: Absolute path or path relative to the search directory.
        search_dir: Directory used to resolve relative paths.

    Returns:
        Existing path.

    Raises:
        FileNotFoundError: If neither candidate exists.
    """
    path = Path(data_file).expanduser()
    if path.is_absolute() and path.exists():
        return path
    resolved = Path(search_dir) / data_file
    if resolved.exists():
        return resolved
    raise FileNotFoundError(f"Ground station data file not found: {data_file!r}")


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
    candidate = candidate.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise SavePathError(f"Save path must be inside {root}") from exc

    if candidate.is_dir() or candidate.suffix == "":
        candidate = candidate / f"{safe_project_filename(project_name)}.json"
    return candidate
