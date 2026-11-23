"""The generated scenario YAML must satisfy the core v0.3.2 parser."""

from pathlib import Path

from satgonetem.experiment.scenario import Scenario

DEFAULT_BUILDER_YAML = """\
name: 'Demo Experiment'
duration_s: 30
tick_s: 1
routing: static
metrics_interval_s: 5
connectivity: false
shells:
  - identifier: LEO
    planes: 3
    satellites_per_plane: 4
    inclination_deg: 53
    revs_per_day: 15.5
    pattern: star
ground_stations:
  - name: Berlin
    latitude: 52.52
    longitude: 13.405
    elevation_km: 0.034
"""


def test_generated_default_yaml_parses_in_core(tmp_path: Path) -> None:
    """The builder's default output is a valid core scenario."""
    path = tmp_path / "scenario.yaml"
    path.write_text(DEFAULT_BUILDER_YAML, encoding="utf-8")

    scenario = Scenario.from_file(path)

    assert scenario.name == "Demo Experiment"
    assert scenario.duration_s == 30
    assert len(scenario.shells) == 1
    assert scenario.shells[0].identifier == "LEO"
    assert len(scenario.ground_stations) == 1
    assert scenario.ground_stations[0].name == "Berlin"
    assert scenario.connectivity is False


def test_generated_quoted_names_parse_in_core(tmp_path: Path) -> None:
    """Single-quoted names with apostrophes remain valid YAML."""
    content = DEFAULT_BUILDER_YAML.replace(
        "name: 'Demo Experiment'",
        "name: 'O''Reilly Demo'",
    ).replace("  - name: Berlin", "  - name: 'St. John''s'")
    path = tmp_path / "scenario.yaml"
    path.write_text(content, encoding="utf-8")

    scenario = Scenario.from_file(path)

    assert scenario.name == "O'Reilly Demo"
    assert scenario.ground_stations[0].name == "St. John's"
