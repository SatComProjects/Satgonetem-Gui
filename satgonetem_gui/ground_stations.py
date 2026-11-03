"""Ground-station CSV parsing and temporary file output."""

import os
import tempfile
from pathlib import Path
from typing import Any


def parse_ground_station_file(path: Path) -> list[dict[str, Any]]:
    """Parse a CSV ground-station file into station dictionaries.

    Args:
        path: File with rows of ``index,name,latitude,longitude,elevation_km``.

    Returns:
        Valid rows as dictionaries. Blank and malformed rows are skipped.
    """
    stations: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",", 4)
            if len(parts) < 5:
                continue
            try:
                stations.append(
                    {
                        "index": int(parts[0]),
                        "name": parts[1].strip(),
                        "latitude": float(parts[2]),
                        "longitude": float(parts[3]),
                        "elevation_km": float(parts[4]),
                    }
                )
            except ValueError:
                continue
    return stations


def write_stations_to_temp(stations: list[dict[str, Any]]) -> Path:
    """Write inline stations to a uniquely named temporary CSV file.

    Args:
        stations: Station dictionaries with index, name, latitude, longitude,
            and elevation_km keys.

    Returns:
        Path to the created file. The caller owns cleanup.
    """
    descriptor, name = tempfile.mkstemp(prefix="satgonetem-gs-", suffix=".csv")
    path = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            for station in stations:
                handle.write(
                    f"{station['index']},{station['name']},{station['latitude']},"
                    f"{station['longitude']},{station['elevation_km']}\n"
                )
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path
