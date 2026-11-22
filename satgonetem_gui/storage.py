"""Filesystem path resolution and save-root policy."""

import hashlib
import os
import re
import tempfile
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
    """Convert a project name into a collision-resistant safe path component."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", project_name).strip("._-")
    digest = hashlib.sha256(project_name.encode("utf-8")).hexdigest()[:8]
    if not cleaned:
        return f"project-{digest}"
    if cleaned != project_name or re.search(r"-[0-9a-f]{8}$", cleaned):
        cleaned = f"{cleaned}-{digest}"
    return cleaned


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

    if candidate.is_dir() or (not candidate.exists() and candidate.suffix == ""):
        candidate = candidate / f"{safe_project_filename(project_name)}.json"
    return candidate


_WORKSPACE_ID_RE = re.compile(r"^[0-9a-f]{16}$")
_WORKSPACE_SCAN_LIMIT = 5000


def workspace_project_id(relative_path: str) -> str:
    """Return an opaque, stable id for a workspace-relative project path."""
    return hashlib.sha256(relative_path.encode("utf-8")).hexdigest()[:16]


def workspace_relative(path: Path, save_root: Path) -> str:
    """Return a POSIX path relative to the workspace root.

    Raises:
        SavePathError: If the path resolves outside the save root.
    """
    root = Path(save_root).expanduser().resolve()
    try:
        resolved = Path(path).expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise SavePathError("Workspace path is invalid.") from exc
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise SavePathError("Workspace path must be inside the save root.") from exc
    return relative.as_posix()


def workspace_filename(name: str) -> str:
    """Return the JSON filename used for a project name in the workspace."""
    return f"{safe_project_filename(name)}.json"


def validate_workspace_target(path: Path, save_root: Path) -> Path:
    """Resolve and contain an existing or new workspace project target.

    Returns:
        The resolved target path.

    Raises:
        SavePathError: If the target is outside the save root, resolves through
            an escaping symlink, or is not a JSON file.
    """
    root = Path(save_root).expanduser().resolve()
    raw = Path(path).expanduser().absolute()
    try:
        raw_parts = raw.relative_to(root).parts
    except ValueError:
        raw_parts = ()
    current = root
    for part in raw_parts:
        current = current / part
        if current.is_symlink():
            raise SavePathError("Workspace target must not be a symlink.")

    candidate = Path(path).expanduser()
    try:
        candidate = candidate.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise SavePathError("Workspace path is invalid.") from exc
    if candidate == root or not _is_within(candidate, root):
        raise SavePathError("Workspace path must be inside the save root.")
    if candidate.suffix.lower() != ".json":
        raise SavePathError("Workspace project files must be JSON.")
    return candidate


def _workspace_json_files(save_root: Path) -> list[Path]:
    """Collect visible, non-symlinked JSON files below the save root."""
    root = Path(save_root).expanduser().resolve()
    if not root.is_dir():
        return []

    pending = [root]
    files: list[Path] = []
    while pending:
        directory = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError:
            continue
        for entry in entries:
            if entry.name.startswith(".") or entry.is_symlink():
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    name = entry.name.lower()
                    if name.endswith(".json") and not name.endswith(".tmp"):
                        files.append(Path(entry.path))
            except OSError:
                continue
    return files


def iter_workspace_project_files(save_root: Path, limit: int = 500) -> list[Path]:
    """Return contained workspace project files, newest modification first.

    Hidden directories/files, symlinks, and temporary ``.tmp`` files are
    skipped. Unreadable entries are ignored instead of failing the listing.
    """
    root = Path(save_root).expanduser().resolve()
    records: list[tuple[float, Path]] = []
    for path in _workspace_json_files(root):
        try:
            resolved = path.resolve()
            if not _is_within(resolved, root):
                continue
            modified = resolved.stat().st_mtime
        except (OSError, RuntimeError):
            continue
        records.append((modified, resolved))

    records.sort(key=lambda record: (-record[0], record[1].as_posix()))
    effective_limit = max(0, int(limit))
    return [path for _, path in records[:effective_limit]]


def resolve_workspace_project(save_root: Path, project_id: str) -> Path | None:
    """Resolve an opaque project id to a contained workspace file.

    Returns ``None`` for a malformed id or when no safe file matches.
    """
    if not isinstance(project_id, str) or not _WORKSPACE_ID_RE.fullmatch(project_id):
        return None
    root = Path(save_root).expanduser().resolve()
    for path in iter_workspace_project_files(root, limit=_WORKSPACE_SCAN_LIMIT):
        if workspace_project_id(workspace_relative(path, root)) == project_id:
            return path
    return None


def write_workspace_project(path: Path, content: str) -> None:
    """Atomically replace a workspace project file with ``content``."""
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
