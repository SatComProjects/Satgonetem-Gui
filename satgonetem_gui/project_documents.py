"""Validation for uploaded project documents before core restoration.

The GUI hands uploaded JSON to the core topology loader. The core restores
embedded ground files before it validates the simulation property, so the GUI
validates the document shape, embedded file names, and data-file paths first.
"""

import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .ground_stations import validate_ground_station_text


class ProjectDocumentError(ValueError):
    """Raised when an uploaded project document is unsafe or malformed."""


def _is_plain_filename(value: object) -> bool:
    """Return whether a value is a single, non-traversing file name."""
    if not isinstance(value, str) or not value:
        return False
    if os.path.isabs(value):
        return False
    if value in {os.curdir, os.pardir} or ".." in value:
        return False
    if "\x00" in value or "/" in value or "\\" in value:
        return False
    if os.sep and os.sep in value:
        return False
    if os.altsep and os.altsep in value:
        return False
    return True


def _resolved_roots(allowed_roots: Iterable[Path]) -> list[Path]:
    return [Path(root).expanduser().resolve() for root in allowed_roots]


def _is_within(path: Path, roots: list[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
        except ValueError:
            continue
        return True
    return False


def _data_file_is_allowed(data_file: str, roots: list[Path]) -> bool:
    """Return whether a data file path resolves inside one of the roots."""
    if not data_file.strip() or "\x00" in data_file:
        return False

    path = Path(data_file).expanduser()
    candidates = [path] if path.is_absolute() else [root / path for root in roots]
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except (OSError, RuntimeError):
            continue
        if _is_within(resolved, roots):
            return True
    return False


def validate_project_document(
    content: str,
    allowed_roots: Iterable[Path],
) -> dict[str, Any]:
    """Validate an uploaded saved-project document before core restoration.

    Args:
        content: Raw JSON text uploaded through the project-load API.
        allowed_roots: Directories where referenced ground-station data files
            may live. Embedded files are exempt because the core rewrites their
            original paths to a private restore directory.

    Returns:
        The parsed document.

    Raises:
        ProjectDocumentError: If the document is not a JSON object, an embedded
            ground file is unsafe, or a referenced data file is outside every
            allowed root.
    """
    try:
        document = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ProjectDocumentError("Project file is not valid JSON.") from exc
    if not isinstance(document, dict):
        raise ProjectDocumentError("Project file must be a JSON object.")

    roots = _resolved_roots(allowed_roots)

    ground_files = document.get("ground_files", {})
    if not isinstance(ground_files, dict):
        raise ProjectDocumentError("Project file has an invalid ground_files section.")
    for original_path, file_info in ground_files.items():
        if not isinstance(original_path, str) or not original_path:
            raise ProjectDocumentError(
                "Project file has an invalid ground_files entry."
            )
        if not isinstance(file_info, dict):
            raise ProjectDocumentError(
                f"Project ground file entry is invalid: {original_path!r}"
            )
        basename = file_info.get("basename")
        if not _is_plain_filename(basename):
            raise ProjectDocumentError(
                "Project ground file basename is not a plain file name: "
                f"{basename!r}"
            )
        file_content = file_info.get("content")
        if not isinstance(file_content, str):
            raise ProjectDocumentError(
                f"Project ground file content must be a string: {original_path!r}"
            )
        try:
            validate_ground_station_text(file_content, original_path)
        except ValueError as exc:
            raise ProjectDocumentError(str(exc)) from exc

    simulation_property = document.get("simulation_property")
    if simulation_property is None:
        return document
    if not isinstance(simulation_property, dict):
        raise ProjectDocumentError(
            "Project file has an invalid simulation_property section."
        )
    ground_objects = simulation_property.get("ground_objects_properties", [])
    if not isinstance(ground_objects, list):
        raise ProjectDocumentError(
            "Project file has invalid ground object properties."
        )
    for ground in ground_objects:
        if not isinstance(ground, dict):
            raise ProjectDocumentError(
                "Project file has an invalid ground object property."
            )
        data_file = ground.get("data_file")
        if not data_file:
            continue
        if not isinstance(data_file, str):
            raise ProjectDocumentError(
                "Project ground object data_file must be a string."
            )
        if data_file in ground_files:
            continue
        if not _data_file_is_allowed(data_file, roots):
            raise ProjectDocumentError(
                "Project ground object data_file is outside the allowed "
                f"directories: {data_file!r}"
            )
    return document
