"""Verify runtime data is available from the package itself."""

from importlib.resources import files

from satgonetem_gui.ground_stations import parse_ground_station_file
from satgonetem_gui.resources import GROUND_STATIONS_DIR, SECURITY_DIR


def test_security_range_preset_is_bundled() -> None:
    """The SatSec classroom range ships with the package."""
    preset = SECURITY_DIR / "range.json"

    assert preset.is_file()
    assert "SatSecRange" in preset.read_text(encoding="utf-8")


def test_ground_station_presets_are_bundled() -> None:
    """Preset files live in package data, not a repository-only directory."""
    presets = sorted(GROUND_STATIONS_DIR.glob("*.txt"))
    names = {path.name for path in presets}

    assert {"100_ground_stations.txt", "representative.txt", "starlink.txt"} <= names
    stations = parse_ground_station_file(GROUND_STATIONS_DIR / "representative.txt")
    assert stations


def test_sample_gonetem_config_is_bundled() -> None:
    """The sample GoNetEm configuration is part of the installed package."""
    config = files("satgonetem_gui").joinpath("data/gonetem_config/config.yaml")

    assert config.is_file()
    assert "docker" in config.read_text(encoding="utf-8")
