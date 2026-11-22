"""Unit tests for the SatGoNetem experiment adapter."""

import importlib.metadata
from types import SimpleNamespace

import pytest

from satgonetem_gui.adapters.experiment_adapter import (
    SatGoNetemExperimentAdapter,
)

MINIMAL_SCENARIO = """\
name: Adapter Experiment
duration_s: 5
tick_s: 1
shells:
  - identifier: LEO
    planes: 2
    satellites_per_plane: 2
"""


def _write_scenario(directory, text: str = MINIMAL_SCENARIO):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "scenario.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_validate_scenario_returns_counts(tmp_path) -> None:
    """A valid scenario yields the compact validation summary."""
    adapter = SatGoNetemExperimentAdapter()
    path = _write_scenario(tmp_path / "run")

    details = adapter.validate_scenario(path)

    assert details == {
        "name": "Adapter Experiment",
        "shells": 1,
        "ground_stations": 0,
        "traffic": 0,
        "events": 0,
        "connectivity": False,
        "duration_s": 5,
    }


def test_validate_scenario_rejects_invalid_yaml(tmp_path) -> None:
    """Invalid scenario YAML is converted to a user-facing ValueError."""
    adapter = SatGoNetemExperimentAdapter()
    path = _write_scenario(tmp_path / "run", "name: [unterminated")

    with pytest.raises(ValueError) as error:
        adapter.validate_scenario(path)

    assert "scenario" in str(error.value).lower()


def test_validate_scenario_rejects_missing_file(tmp_path) -> None:
    """A missing scenario file is converted to a user-facing ValueError."""
    adapter = SatGoNetemExperimentAdapter()

    with pytest.raises(ValueError) as error:
        adapter.validate_scenario(tmp_path / "missing.yaml")

    assert "scenario" in str(error.value).lower()


class FakeRunner:
    """Experiment runner double that records run arguments."""

    def __init__(self, inspect_empty: bool = False) -> None:
        self.calls: list[dict] = []
        self.inspect_empty = inspect_empty

    def run(self, **kwargs):
        if self.inspect_empty:
            assert list(kwargs["output_dir"].iterdir()) == []
        self.calls.append(kwargs)
        return SimpleNamespace(
            summary={"mode": "test"},
            errors=["warning"],
        )


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("dry_run", {"live": False, "dry_run": True}),
        ("offline", {"live": False}),
        ("live", {"live": True}),
    ],
)
def test_run_scenario_maps_modes(tmp_path, mode: str, expected: dict) -> None:
    """Each mode maps to the core runner flags from the specification."""
    run_dir = tmp_path / "run"
    path = _write_scenario(run_dir)
    runner = FakeRunner()
    seen = []

    def factory(scenario):
        seen.append(scenario)
        return runner

    adapter = SatGoNetemExperimentAdapter(runner_factory=factory)

    result = adapter.run_scenario(path, run_dir, mode)

    assert len(seen) == 1
    assert runner.calls == [{"output_dir": run_dir, **expected}]
    assert result == {"summary": {"mode": "test"}, "errors": ["warning"]}
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == MINIMAL_SCENARIO


def test_run_scenario_keeps_the_run_directory_empty_for_the_runner(tmp_path) -> None:
    """The submitted YAML is hidden so the core runner stays in its run dir."""
    run_dir = tmp_path / "run"
    path = _write_scenario(run_dir)
    runner = FakeRunner(inspect_empty=True)
    adapter = SatGoNetemExperimentAdapter(runner_factory=lambda _scenario: runner)

    adapter.run_scenario(path, run_dir, "offline")

    assert runner.calls
    assert (run_dir / "scenario.yaml").is_file()


def test_run_scenario_rejects_unknown_mode(tmp_path) -> None:
    """Unknown modes never reach the core runner."""
    run_dir = tmp_path / "run"
    path = _write_scenario(run_dir)
    runner = FakeRunner()
    adapter = SatGoNetemExperimentAdapter(runner_factory=lambda _scenario: runner)

    with pytest.raises(ValueError):
        adapter.run_scenario(path, run_dir, "bogus")

    assert runner.calls == []


def test_run_scenario_rejects_a_non_empty_run_directory(tmp_path) -> None:
    """Stray files cannot push core runner output into a sibling directory."""
    run_dir = tmp_path / "run"
    path = _write_scenario(run_dir)
    (run_dir / "stray.txt").write_text("stray", encoding="utf-8")
    runner = FakeRunner()
    adapter = SatGoNetemExperimentAdapter(runner_factory=lambda _scenario: runner)

    with pytest.raises(ValueError) as error:
        adapter.run_scenario(path, run_dir, "offline")

    assert "empty" in str(error.value).lower()
    assert runner.calls == []
    assert path.is_file()


def test_core_version_reports_installed_package() -> None:
    """The adapter reports the installed SatGoNetem version."""
    adapter = SatGoNetemExperimentAdapter()

    assert adapter.core_version() == importlib.metadata.version("satgonetem")
