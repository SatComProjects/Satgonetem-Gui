"""Tests for ground-station file parsing and safe CSV output."""

import csv
from pathlib import Path

import pytest

from satgonetem_gui.ground_stations import (
    parse_ground_station_file,
    stable_ground_stations_dir,
    validate_inline_stations,
    write_stations_to_temp,
)

STATIONS = [
    {
        "index": 0,
        "name": "Berlin",
        "latitude": 52.52,
        "longitude": 13.405,
        "elevation_km": 0.034,
    },
    {
        "index": 1,
        "name": "Paris",
        "latitude": 48.8566,
        "longitude": 2.3522,
        "elevation_km": 0.035,
    },
]


def test_parse_ground_station_file_skips_invalid_rows(tmp_path: Path) -> None:
    """Blank and malformed rows are ignored without failing the whole file."""
    path = tmp_path / "stations.txt"
    path.write_text(
        "0,Berlin,52.52,13.405,0.034\nnot,a,valid,row\n\n1,Paris,48.8566,2.3522,0.035\n",
        encoding="utf-8",
    )

    stations = parse_ground_station_file(path)

    assert [station["name"] for station in stations] == ["Berlin", "Paris"]
    assert stations[0]["latitude"] == 52.52
    assert stations[1]["elevation_km"] == 0.035


def test_parse_ground_station_file_handles_quoted_fields_and_bom(
    tmp_path: Path,
) -> None:
    """Quoted commas and newlines are parsed and a UTF-8 BOM is tolerated."""
    path = tmp_path / "quoted.txt"
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([0, "Berlin, DE", 52.52, 13.405, 0.034])
        writer.writerow([1, "Paris\nOffice", 48.8566, 2.3522, 0.035])

    stations = parse_ground_station_file(path)

    assert [station["name"] for station in stations] == [
        "Berlin, DE",
        "Paris\nOffice",
    ]


def test_validate_inline_stations_rejects_core_incompatible_names() -> None:
    """Comma and newline names fail with a message the UI can display."""
    for name in ("Berlin, DE", "Berlin\nDE", "Berlin\rDE"):
        station = dict(STATIONS[0], name=name)
        with pytest.raises(
            ValueError,
            match="must not contain commas or newlines",
        ):
            validate_inline_stations([station])


def test_validate_inline_stations_requires_fields_and_numeric_coordinates() -> None:
    """Missing keys and non-numeric coordinates are rejected before writing."""
    with pytest.raises(ValueError, match="missing required fields"):
        validate_inline_stations([{"index": 0, "name": "Berlin"}])

    station = dict(STATIONS[0], latitude="north")
    with pytest.raises(ValueError, match="must be numeric"):
        validate_inline_stations([station])


def test_write_stations_to_temp_uses_unique_files(tmp_path: Path) -> None:
    """Inline station data is written to unique files in the chosen directory."""
    first = write_stations_to_temp(STATIONS, directory=tmp_path)
    second = write_stations_to_temp(STATIONS, directory=tmp_path)
    try:
        assert first != second
        assert first.parent == tmp_path
        assert second.parent == tmp_path
        assert first.exists()
        assert second.exists()
        assert [station["name"] for station in parse_ground_station_file(first)] == [
            "Berlin",
            "Paris",
        ]
    finally:
        first.unlink(missing_ok=True)
        second.unlink(missing_ok=True)


def test_write_stations_to_temp_quotes_allowed_special_characters(
    tmp_path: Path,
) -> None:
    """Quotation marks stay intact while remaining core-compatible."""
    stations = [dict(STATIONS[0], name='Berlin "Mitte"')]

    path = write_stations_to_temp(stations, directory=tmp_path)
    try:
        assert path.read_text(encoding="utf-8") == ('0,"Berlin ""Mitte""",52.52,13.405,0.034\n')
        assert parse_ground_station_file(path)[0]["name"] == 'Berlin "Mitte"'
    finally:
        path.unlink(missing_ok=True)


def test_write_stations_to_temp_rejects_comma_names(tmp_path: Path) -> None:
    """The write layer gives a clear error instead of a core column error."""
    stations = [dict(STATIONS[0], name="Berlin, DE")]

    with pytest.raises(ValueError, match="must not contain commas or newlines"):
        write_stations_to_temp(stations, directory=tmp_path)


def test_stable_ground_stations_dir_lives_under_save_root(tmp_path: Path) -> None:
    """Persisted station files use the managed save-root directory."""
    save_root = tmp_path / "projects"

    assert stable_ground_stations_dir(save_root) == (save_root / ".satgonetem" / "ground_stations")
