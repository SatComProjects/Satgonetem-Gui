"""Verify runtime data is available from the package itself."""

from importlib.resources import files

from satgonetem_gui.ground_stations import (
    parse_ground_station_file,
    validate_inline_stations,
)
from satgonetem_gui.resources import GROUND_STATIONS_DIR


def test_ground_station_presets_are_bundled() -> None:
    """Preset files live in package data, not a repository-only directory."""
    presets = sorted(GROUND_STATIONS_DIR.glob("*.txt"))
    names = {path.name for path in presets}

    assert {"100_ground_stations.txt", "representative.txt", "starlink.txt"} <= names
    stations = parse_ground_station_file(GROUND_STATIONS_DIR / "representative.txt")
    assert stations


def test_all_bundled_station_presets_validate() -> None:
    """Every shipped preset can be selected and submitted to the core."""
    for path in sorted(GROUND_STATIONS_DIR.glob("*.txt")):
        validate_inline_stations(parse_ground_station_file(path))


def test_sample_gonetem_config_is_bundled() -> None:
    """The sample GoNetEm configuration is part of the installed package."""
    config = files("satgonetem_gui").joinpath("data/gonetem_config/config.yaml")

    assert config.is_file()
    assert "docker" in config.read_text(encoding="utf-8")
