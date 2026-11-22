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

from .ground_stations import validate_ground_station_text, validate_inline_stations
from .storage import resolve_data_file


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
        if _is_within(resolved, roots) and resolved.is_file():
            return True
    return False


def validate_project_create_payload(
    shells: object,
    grounds: object,
    data_search_dir: Path | None = None,
    allowed_roots: Iterable[Path] = (),
) -> None:
    """Validate the nested shapes accepted by the project-create form.

    The request schema validates that the hidden fields contain JSON arrays;
    this function validates their elements before a background build starts, so
    malformed input is a 422 instead of a late project-state error.

    Args:
        shells: Parsed orbit-shell objects.
        grounds: Parsed ground-object objects.
        data_search_dir: Directory used to resolve relative ``data_file``
            values. When omitted, referenced files are not checked.
        allowed_roots: Additional directories where data files may live.
    """
    if not isinstance(shells, list) or not shells:
        raise ValueError("At least one orbit shell is required.")
    for shell in shells:
        if not isinstance(shell, dict):
            raise ValueError("Each orbit shell must be an object.")
        for field in (
            "type",
            "constellation_property",
            "orbital_connectivity_property",
            "ground_object_white_list",
        ):
            if field not in shell:
                raise ValueError(f"Orbit shell is missing {field}.")
        if not isinstance(shell["type"], str) or not shell["type"].strip():
            raise ValueError("Orbit shell type must be a string.")
        if not isinstance(shell["constellation_property"], dict):
            raise ValueError("Orbit shell constellation_property must be an object.")
        constellation = shell["constellation_property"]
        identifier = constellation.get("identifier")
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError("Orbit shell identifier must be a non-empty string.")
        planes = constellation.get("amount_of_orbit_plane")
        satellites = constellation.get("amount_of_satellite_per_orbit_plane")
        if (
            not isinstance(planes, int)
            or isinstance(planes, bool)
            or not 1 <= planes <= 1000
        ):
            raise ValueError(
                "Orbit shell amount_of_orbit_plane must be an integer between "
                "1 and 1000."
            )
        if (
            not isinstance(satellites, int)
            or isinstance(satellites, bool)
            or not 1 <= satellites <= 1000
        ):
            raise ValueError(
                "Orbit shell amount_of_satellite_per_orbit_plane must be an "
                "integer between 1 and 1000."
            )
        if planes * satellites > 10_000:
            raise ValueError("An orbit shell cannot exceed 10000 satellites.")
        inclination = constellation.get("inclination")
        if (
            not isinstance(inclination, (int, float))
            or isinstance(inclination, bool)
            or not 0 <= inclination <= 180
        ):
            raise ValueError(
                "Orbit shell inclination must be between 0 and 180 degrees."
            )
        revolutions = constellation.get("mean_revolution_per_day")
        if (
            not isinstance(revolutions, (int, float))
            or isinstance(revolutions, bool)
            or not 0 <= revolutions <= 100
        ):
            raise ValueError(
                "Orbit shell mean_revolution_per_day must be between 0 and 100."
            )
        if not isinstance(shell["orbital_connectivity_property"], dict):
            raise ValueError(
                "Orbit shell orbital_connectivity_property must be an object."
            )
        if not isinstance(shell["ground_object_white_list"], list):
            raise ValueError("Orbit shell ground_object_white_list must be a list.")

    if not isinstance(grounds, list) or not grounds:
        raise ValueError("At least one ground object is required.")
    for ground in grounds:
        if not isinstance(ground, dict):
            raise ValueError("Each ground object must be an object.")
        for field in ("identifier", "type", "connectivity_properties"):
            if field not in ground:
                raise ValueError(f"Ground object is missing {field}.")
        if not isinstance(ground["identifier"], str) or not ground["identifier"].strip():
            raise ValueError("Ground object identifier must be a string.")
        if not isinstance(ground["type"], str) or not ground["type"].strip():
            raise ValueError("Ground object type must be a string.")
        if not isinstance(ground["connectivity_properties"], dict):
            raise ValueError("Ground object connectivity_properties must be an object.")
        stations = ground.get("stations")
        data_file = ground.get("data_file")
        if stations:
            validate_inline_stations(stations)
        elif not isinstance(data_file, str) or not data_file.strip():
            raise ValueError("Ground object has no stations or data_file.")
        elif data_search_dir is not None:
            try:
                resolve_data_file(
                    data_file,
                    data_search_dir,
                    allowed_roots=allowed_roots,
                )
            except (OSError, ValueError) as exc:
                raise ValueError(
                    "Ground object data_file is not a readable station file: "
                    f"{data_file!r}"
                ) from exc


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
    basenames: set[str] = set()
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
        if basename in basenames:
            raise ProjectDocumentError(
                "Project ground file basenames must be unique: "
                f"{basename!r}"
            )
        basenames.add(basename)
        file_content = file_info.get("content")
        if not isinstance(file_content, str):
            raise ProjectDocumentError(
                f"Project ground file content must be a string: {original_path!r}"
            )
        try:
            validate_ground_station_text(file_content, original_path)
        except ValueError as exc:
            raise ProjectDocumentError(str(exc)) from exc

    network_config = document.get("network_config")
    if network_config is not None and not isinstance(network_config, dict):
        raise ProjectDocumentError(
            "Project file has an invalid network_config section."
        )
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
        if not Path(data_file).expanduser().is_absolute():
            raise ProjectDocumentError(
                "Project ground object data_file must be absolute unless it "
                f"is embedded in ground_files: {data_file!r}"
            )
        if not _data_file_is_allowed(data_file, roots):
            raise ProjectDocumentError(
                "Project ground object data_file is outside the allowed "
                f"directories: {data_file!r}"
            )
    return document
