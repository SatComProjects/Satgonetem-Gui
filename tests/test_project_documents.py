"""Validation tests for project create/load document shapes."""

import pytest

from satgonetem_gui.project_documents import validate_project_create_payload
from tests.factories import ground_object, walker_shell


def _shell(**overrides):
    shell = walker_shell()
    shell["constellation_property"].update(overrides)
    return shell


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("amount_of_orbit_plane", 0),
        ("amount_of_orbit_plane", 1001),
        ("amount_of_orbit_plane", 2.5),
        ("amount_of_orbit_plane", True),
        ("amount_of_satellite_per_orbit_plane", 0),
        ("amount_of_satellite_per_orbit_plane", 1001),
        ("inclination", -1),
        ("inclination", 181),
        ("mean_revolution_per_day", -1),
        ("mean_revolution_per_day", 101),
        ("identifier", ""),
    ],
)
def test_create_rejects_invalid_constellation_values(field, value) -> None:
    """Unbounded or malformed shell dimensions fail before the build starts."""
    with pytest.raises(ValueError):
        validate_project_create_payload([_shell(**{field: value})], [ground_object()])


def test_create_rejects_an_oversized_constellation() -> None:
    """Each dimension can be valid while the product is still too large."""
    shell = _shell(
        amount_of_orbit_plane=1000,
        amount_of_satellite_per_orbit_plane=1000,
    )

    with pytest.raises(ValueError, match="10000"):
        validate_project_create_payload([shell], [ground_object()])
