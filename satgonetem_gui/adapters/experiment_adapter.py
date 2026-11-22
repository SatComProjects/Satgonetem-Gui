"""SatGoNetem experiment adapter.

This is the only module that imports ``satgonetem.experiment``. Services use
the narrow :class:`~satgonetem_gui.services.ports.ExperimentGateway` protocol.
"""

import importlib.metadata
import logging
import os
from pathlib import Path
from typing import Any, Callable

from satgonetem.experiment.runner import ExperimentRunner
from satgonetem.experiment.scenario import Scenario, ScenarioError

logger = logging.getLogger(__name__)

MODES = frozenset({"dry_run", "offline", "live"})
SCENARIO_FILENAME = "scenario.yaml"


class SatGoNetemExperimentAdapter:
    """Concrete adapter around the core scenario loader and experiment runner."""

    def __init__(
        self,
        runner_factory: Callable[[Scenario], Any] | None = None,
    ) -> None:
        self._runner_factory = runner_factory or ExperimentRunner

    def validate_scenario(self, path: Path) -> dict[str, Any]:
        """Load and validate one scenario, returning a compact summary."""
        try:
            scenario = Scenario.from_file(path)
        except ScenarioError as exc:
            raise ValueError(f"Invalid experiment scenario: {exc}") from exc
        except FileNotFoundError as exc:
            raise ValueError("Experiment scenario file was not found.") from exc
        except OSError as exc:
            raise ValueError("Could not read the experiment scenario file.") from exc

        return {
            "name": scenario.name,
            "shells": len(scenario.shells),
            "ground_stations": len(scenario.ground_stations),
            "traffic": len(scenario.traffic),
            "events": len(scenario.events),
            "connectivity": bool(scenario.connectivity),
            "duration_s": scenario.duration_s,
        }

    def run_scenario(
        self,
        path: Path,
        run_dir: Path,
        mode: str,
    ) -> dict[str, Any]:
        """Run one scenario into ``run_dir`` and return its summary and errors."""
        if mode not in MODES:
            raise ValueError(f"Unsupported experiment mode: {mode!r}")

        scenario_path = Path(path)
        target_dir = Path(run_dir)
        try:
            scenario = Scenario.from_file(scenario_path)
        except ScenarioError as exc:
            raise ValueError(f"Invalid experiment scenario: {exc}") from exc
        except FileNotFoundError as exc:
            raise ValueError("Experiment scenario file was not found.") from exc
        except OSError as exc:
            raise ValueError("Could not read the experiment scenario file.") from exc

        if not target_dir.is_dir():
            raise ValueError("Experiment run directory does not exist.")

        # The core runner treats a non-empty output directory as a collision
        # and writes to a suffixed sibling. Move the submitted YAML aside so
        # every artifact lands inside the caller-provided run directory, then
        # restore it for diagnosis and artifact serving.
        hidden_path: Path | None = None
        if self._same_file(scenario_path, target_dir / SCENARIO_FILENAME):
            hidden_path = target_dir.parent / f".{target_dir.name}.{SCENARIO_FILENAME}"
            hidden_path.unlink(missing_ok=True)
            os.replace(scenario_path, hidden_path)

        kwargs: dict[str, Any] = {"output_dir": target_dir}
        if mode == "dry_run":
            kwargs["live"] = False
            kwargs["dry_run"] = True
        elif mode == "offline":
            kwargs["live"] = False
        else:
            kwargs["live"] = True

        try:
            if any(target_dir.iterdir()):
                raise ValueError("Experiment run directory must be empty before a run.")
            runner = self._runner_factory(scenario)
            result = runner.run(**kwargs)
        finally:
            if hidden_path is not None and hidden_path.exists():
                os.replace(hidden_path, scenario_path)

        summary = getattr(result, "summary", None)
        if not isinstance(summary, dict):
            raise RuntimeError("Experiment runner returned an invalid summary.")
        errors = getattr(result, "errors", []) or []
        if not isinstance(errors, (list, tuple)):
            errors = [str(errors)]
        return {
            "summary": summary,
            "errors": [str(error) for error in errors],
        }

    def core_version(self) -> str:
        """Return the installed SatGoNetem version."""
        try:
            return importlib.metadata.version("satgonetem")
        except importlib.metadata.PackageNotFoundError:
            try:
                import satgonetem
            except ImportError:  # pragma: no cover - import already succeeded
                return "unknown"
            return str(getattr(satgonetem, "__version__", "unknown"))

    @staticmethod
    def _same_file(left: Path, right: Path) -> bool:
        """Return whether two paths point at the same location."""
        try:
            return left.expanduser().resolve() == right.expanduser().resolve()
        except (OSError, RuntimeError):
            return False
