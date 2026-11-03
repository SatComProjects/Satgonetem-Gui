"""Access to data files bundled inside the installed package."""

from importlib.resources import files
from pathlib import Path


def package_path(*parts: str) -> Path:
    """Return the filesystem path of a bundled package resource."""
    resource = files("satgonetem_gui")
    for part in parts:
        resource = resource.joinpath(part)
    return Path(str(resource))


GROUND_STATIONS_DIR = package_path("data", "ground_stations")
SECURITY_DIR = package_path("data", "security")
