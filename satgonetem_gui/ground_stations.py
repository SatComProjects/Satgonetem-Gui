"""Ground-station CSV parsing and file output."""

import csv
import os
import tempfile
from pathlib import Path
from typing import Any

STATION_FIELDS = ("index", "name", "latitude", "longitude", "elevation_m")
_FORBIDDEN_NAME_CHARACTERS = (",", "\r", "\n")


def parse_ground_station_file(path: Path) -> list[dict[str, Any]]:
    """Parse a CSV ground-station file into station dictionaries.

    Args:
        path: File with rows of ``index,name,latitude,longitude,elevation_m``.

    Returns:
        Valid rows as dictionaries. Blank and malformed rows are skipped.
    """
    stations: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            if not row or all(not field.strip() for field in row):
                continue
            if len(row) != len(STATION_FIELDS):
                continue
            try:
                stations.append(
                    {
                        "index": int(row[0].strip()),
                        "name": row[1].strip(),
                        "latitude": float(row[2].strip()),
                        "longitude": float(row[3].strip()),
                        "elevation_m": float(row[4].strip()),
                    }
                )
            except ValueError:
                continue
    return stations


def validate_inline_stations(stations: object) -> list[dict[str, Any]]:
    """Validate inline station dictionaries before writing a core-readable file.

    SatGoNetem parses ground-station files with ``line.split(",")``, so a name
    containing a comma or a line break cannot be represented safely. Fail here
    with a clear message instead of letting the core report a column-count
    error after the project build has already started.

    Args:
        stations: Candidate station dictionaries from a project create request.

    Returns:
        Normalized station dictionaries.

    Raises:
        ValueError: If the value is not a list of station dictionaries with
            numeric coordinates and core-compatible names.
    """
    if not isinstance(stations, list):
        raise ValueError("Ground stations must be a list.")

    validated: list[dict[str, Any]] = []
    for station in stations:
        if not isinstance(station, dict):
            raise ValueError("Each ground station must be an object.")
        missing = [field for field in STATION_FIELDS if field not in station]
        if missing:
            raise ValueError(
                "Ground station is missing required fields: "
                + ", ".join(missing)
                + "."
            )
        name = station["name"]
        if not isinstance(name, str):
            raise ValueError("Ground station names must be strings.")
        if any(character in name for character in _FORBIDDEN_NAME_CHARACTERS):
            raise ValueError(
                "Ground station names must not contain commas or newlines."
            )
        try:
            index = int(station["index"])
            latitude = float(station["latitude"])
            longitude = float(station["longitude"])
            elevation_m = float(station["elevation_m"])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Ground station index and coordinates must be numeric."
            ) from exc
        validated.append(
            {
                "index": index,
                "name": name,
                "latitude": latitude,
                "longitude": longitude,
                "elevation_m": elevation_m,
            }
        )
    return validated


def validate_ground_station_text(content: str, source: str = "ground file") -> None:
    """Validate embedded ground-station content against the core parser.

    The core reads one station per line with ``line.split(",")`` and requires
    exactly five columns. This mirrors that contract so an uploaded project
    fails with a clear message instead of an opaque core error.

    Args:
        content: Station file content embedded in a saved project.
        source: Human-readable description used in error messages.

    Raises:
        ValueError: If a row is malformed or a name contains a comma/newline.
    """
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            raise ValueError(
                f"{source} line {line_number} is blank; expected five columns."
            )
        parts = line.split(",")
        if len(parts) != len(STATION_FIELDS):
            raise ValueError(
                f"{source} line {line_number} must have five comma-separated "
                "columns."
            )
        if any(character in parts[1] for character in _FORBIDDEN_NAME_CHARACTERS):
            raise ValueError(
                "Ground station names must not contain commas or newlines."
            )
        try:
            int(parts[0])
            float(parts[2])
            float(parts[3])
            float(parts[4])
        except ValueError as exc:
            raise ValueError(
                f"{source} line {line_number} has non-numeric index or coordinates."
            ) from exc


def stable_ground_stations_dir(save_root: Path) -> Path:
    """Return the managed directory for persisted ground-station files."""
    return Path(save_root).expanduser() / ".satgonetem" / "ground_stations"


def write_stations_to_temp(
    stations: list[dict[str, Any]],
    directory: Path | None = None,
) -> Path:
    """Write inline stations to a uniquely named CSV file.

    Args:
        stations: Station dictionaries with index, name, latitude, longitude,
            and elevation_m keys.
        directory: Destination directory. When omitted, the system temporary
            directory is used. The directory is created when missing.

    Returns:
        Path to the created file. The caller owns cleanup.

    Raises:
        ValueError: If the station data cannot be read safely by the core.
    """
    validated = validate_inline_stations(stations)
    target_dir: Path | None = None
    if directory is not None:
        target_dir = Path(directory).expanduser()
        target_dir.mkdir(parents=True, exist_ok=True)

    descriptor, name = tempfile.mkstemp(
        prefix="satgonetem-gs-",
        suffix=".csv",
        dir=target_dir,
    )
    path = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            for station in validated:
                writer.writerow([station[field] for field in STATION_FIELDS])
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path
