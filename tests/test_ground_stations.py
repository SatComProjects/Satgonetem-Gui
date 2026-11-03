"""Tests for ground-station file parsing and safe temporary output."""

from pathlib import Path

from satgonetem_gui.ground_stations import (
    parse_ground_station_file,
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


def test_write_stations_to_temp_uses_unique_files() -> None:
    """Inline station data is written to unique temporary files."""
    first = write_stations_to_temp(STATIONS)
    second = write_stations_to_temp(STATIONS)
    try:
        assert first != second
        assert first.exists()
        assert second.exists()
        assert [station["name"] for station in parse_ground_station_file(first)] == [
            "Berlin",
            "Paris",
        ]
    finally:
        first.unlink(missing_ok=True)
        second.unlink(missing_ok=True)
