"""Unit tests for experiment run orchestration and artifacts."""

import hashlib
import json
import threading
import time

import pytest

from satgonetem_gui.config import Settings
from satgonetem_gui.errors import APIError
from satgonetem_gui.schemas import ExperimentStartRequest
from satgonetem_gui.services.experiment_service import ExperimentService
from satgonetem_gui.state import ProjectSession

MINIMAL_EXPERIMENT_YAML = """\
name: Service Experiment
duration_s: 5
tick_s: 1
shells:
  - identifier: LEO
    planes: 2
    satellites_per_plane: 2
"""


class FakeExperimentTopology:
    """Minimal topology state used by the live-run guard."""

    def __init__(self, running: bool = False) -> None:
        self.running = running
        self.session = ProjectSession()

    def network_running(self) -> bool:
        return self.running

    def begin_network_operation(self) -> bool:
        return self.session.begin_network_operation()

    def end_network_operation(self) -> None:
        self.session.end_network_operation()


class FakeExperimentGateway:
    """In-memory experiment gateway with recording and failure hooks."""

    def __init__(
        self,
        name: str = "Test Experiment",
        errors: list[str] | None = None,
        run_error: Exception | None = None,
        validate_error: Exception | None = None,
    ) -> None:
        self.name = name
        self.errors = list(errors or [])
        self.run_error = run_error
        self.validate_error = validate_error
        self.validated: list = []
        self.runs: list = []

    def validate_scenario(self, path):
        self.validated.append(path)
        if self.validate_error is not None:
            raise self.validate_error
        return {
            "name": self.name,
            "shells": 1,
            "ground_stations": 0,
            "traffic": 0,
            "events": 0,
            "connectivity": False,
            "duration_s": 5,
        }

    def run_scenario(self, path, run_dir, mode):
        self.runs.append((path, run_dir, mode))
        if self.run_error is not None:
            raise self.run_error
        return {
            "summary": {"flows": {"count": 0}, "mode": mode},
            "errors": list(self.errors),
        }

    def core_version(self) -> str:
        return "0.3.2-test"


class BlockingExperimentGateway(FakeExperimentGateway):
    """Gateway whose runs block until the test releases them."""

    def __init__(self, wait_for: int = 1) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()
        self._run_lock = threading.Lock()
        self._wait_for = wait_for
        self._started_count = 0

    def run_scenario(self, path, run_dir, mode):
        self.runs.append((path, run_dir, mode))
        with self._run_lock:
            self._started_count += 1
            if self._started_count >= self._wait_for:
                self.started.set()
        assert self.release.wait(timeout=5)
        return {"summary": {"flows": 0, "mode": mode}, "errors": []}


def _experiment_payload(mode: str = "offline") -> ExperimentStartRequest:
    return ExperimentStartRequest(scenario_yaml=MINIMAL_EXPERIMENT_YAML, mode=mode)


def _experiment_service(
    save_root,
    gateway: FakeExperimentGateway,
    *,
    network_running: bool = False,
) -> ExperimentService:
    return ExperimentService(
        Settings("127.0.0.1", 8000, save_root),
        FakeExperimentTopology(running=network_running),
        gateway,
    )


def _wait_for_experiment(
    service: ExperimentService,
    run_id: str,
    timeout: float = 5.0,
) -> dict:
    deadline = time.monotonic() + timeout
    status = None
    while time.monotonic() < deadline:
        status = service.status(run_id)
        if status["status"] != "running":
            return status
        time.sleep(0.01)
    raise AssertionError(f"experiment did not finish: {status}")


@pytest.mark.parametrize("mode", ["dry_run", "offline"])
def test_experiment_start_and_status_done(tmp_path, mode: str) -> None:
    """Dry and offline starts run the gateway and finish in the background."""
    gateway = FakeExperimentGateway()
    service = _experiment_service(tmp_path / mode, gateway)

    run_id = service.start(_experiment_payload(mode))
    status = _wait_for_experiment(service, run_id)

    assert run_id.startswith("exp-")
    assert status["status"] == "done"
    assert status["mode"] == mode
    assert status["name"] == "Test Experiment"
    assert status["summary"]["mode"] == mode
    assert status["finished_at"] is not None
    assert gateway.runs[0][2] == mode
    assert gateway.validated


def test_experiment_list_and_artifact_round_trip(tmp_path) -> None:
    """Completed runs are listed newest first and serve allowlisted artifacts."""
    gateway = FakeExperimentGateway()
    service = _experiment_service(tmp_path, gateway)

    run_id = service.start(_experiment_payload())
    _wait_for_experiment(service, run_id)

    listing = service.list_runs()
    assert listing["ok"] is True
    assert [run["run_id"] for run in listing["runs"]] == [run_id]
    entry = listing["runs"][0]
    assert entry["status"] == "done"
    assert entry["summary"]["mode"] == "offline"
    assert {
        "scenario.yaml",
        "provenance.json",
        "summary.json",
        "errors.json",
    } <= set(entry["artifacts"])
    assert "metrics.jsonl" not in entry["artifacts"]

    artifact = service.artifact(run_id, "summary.json")
    assert artifact["filename"] == "summary.json"
    assert artifact["content_type"] == "application/json"
    assert json.loads(artifact["content"])["mode"] == "offline"
    scenario = service.artifact(run_id, "scenario.yaml")
    assert scenario["content"] == MINIMAL_EXPERIMENT_YAML
    assert scenario["content_type"] == "text/yaml"
    provenance = service.artifact(run_id, "provenance.json")
    assert provenance["content_type"] == "application/json"


def test_experiment_invalid_scenario_is_422_and_cleans_up(tmp_path) -> None:
    """Validation failures return 422 and remove the reserved run directory."""
    gateway = FakeExperimentGateway(validate_error=ValueError("missing shells"))
    service = _experiment_service(tmp_path, gateway)

    with pytest.raises(APIError) as error:
        service.start(_experiment_payload())

    assert error.value.status_code == 422
    assert "missing shells" in error.value.message
    assert (tmp_path / ".satgonetem" / "experiments").is_dir()
    assert list((tmp_path / ".satgonetem" / "experiments").iterdir()) == []


def test_experiment_live_guard_requires_stopped_containers(tmp_path) -> None:
    """Live runs are rejected while GoNetEm containers are up."""
    gateway = FakeExperimentGateway()
    service = _experiment_service(tmp_path, gateway, network_running=True)

    with pytest.raises(APIError) as error:
        service.start(_experiment_payload("live"))

    assert error.value.status_code == 409
    assert "container" in error.value.message.lower()
    assert gateway.validated == []
    assert gateway.runs == []


def test_experiment_live_single_flight(tmp_path) -> None:
    """Only one live run may be active at a time."""
    gateway = BlockingExperimentGateway()
    service = _experiment_service(tmp_path, gateway)

    run_id = service.start(_experiment_payload("live"))
    assert gateway.started.wait(timeout=5)
    try:
        with pytest.raises(APIError) as error:
            service.start(_experiment_payload("live"))
        assert error.value.status_code == 409
    finally:
        gateway.release.set()

    assert _wait_for_experiment(service, run_id)["status"] == "done"


def test_experiment_capacity_limit_is_429(tmp_path) -> None:
    """At most two runs execute at once, and finished runs free their slot."""
    gateway = BlockingExperimentGateway(wait_for=2)
    service = _experiment_service(tmp_path, gateway)

    first = service.start(_experiment_payload("offline"))
    second = service.start(_experiment_payload("dry_run"))
    assert gateway.started.wait(timeout=5)
    try:
        with pytest.raises(APIError) as error:
            service.start(_experiment_payload("offline"))
        assert error.value.status_code == 429
    finally:
        gateway.release.set()

    assert _wait_for_experiment(service, first)["status"] == "done"
    assert _wait_for_experiment(service, second)["status"] == "done"

    third = service.start(_experiment_payload("dry_run"))
    assert _wait_for_experiment(service, third)["status"] == "done"


def test_experiment_artifact_traversal_is_404(tmp_path) -> None:
    """Artifact names and run ids cannot escape their directories."""
    run_id = "exp-unknown"
    gateway = FakeExperimentGateway()
    service = _experiment_service(tmp_path, gateway)
    real_run = service.start(_experiment_payload())
    _wait_for_experiment(service, real_run)

    with pytest.raises(APIError) as error:
        service.artifact(real_run, "../provenance.json")
    assert error.value.status_code == 404

    with pytest.raises(APIError) as error:
        service.artifact(real_run, "scenario.yaml/../../provenance.json")
    assert error.value.status_code == 404

    with pytest.raises(APIError) as error:
        service.artifact("..", "summary.json")
    assert error.value.status_code == 404

    with pytest.raises(APIError) as error:
        service.status("missing")
    assert error.value.status_code == 404

    with pytest.raises(APIError) as error:
        service.artifact(run_id, "summary.json")
    assert error.value.status_code == 404


def test_experiment_artifact_rejects_symlink_escape(tmp_path) -> None:
    """An in-run symlink pointing outside the run directory is not served."""
    gateway = FakeExperimentGateway()
    service = _experiment_service(tmp_path, gateway)
    run_id = service.start(_experiment_payload())
    _wait_for_experiment(service, run_id)

    run_dir = next((tmp_path / ".satgonetem" / "experiments").iterdir())
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    (run_dir / "connectivity.json").symlink_to(outside)

    with pytest.raises(APIError) as error:
        service.artifact(run_id, "connectivity.json")
    assert error.value.status_code == 404
    assert "connectivity.json" not in service.list_runs()["runs"][0]["artifacts"]


def test_experiment_provenance_and_artifact_writes(tmp_path) -> None:
    """Provenance records versions, hashes, and no absolute paths."""
    gateway = FakeExperimentGateway()
    service = _experiment_service(tmp_path, gateway)

    run_id = service.start(_experiment_payload())
    _wait_for_experiment(service, run_id)

    run_dir = next((tmp_path / ".satgonetem" / "experiments").iterdir())
    provenance_text = (run_dir / "provenance.json").read_text(encoding="utf-8")
    provenance = json.loads(provenance_text)
    assert provenance["run_id"] == run_id
    assert provenance["name"] == "Test Experiment"
    assert provenance["mode"] == "offline"
    assert provenance["status"] == "done"
    assert provenance["core_version"] == "0.3.2-test"
    assert provenance["gui_version"]
    assert provenance["scenario_filename"] == "scenario.yaml"
    assert (
        provenance["scenario_sha256"]
        == hashlib.sha256(MINIMAL_EXPERIMENT_YAML.encode("utf-8")).hexdigest()
    )
    assert provenance["started_at"]
    assert provenance["finished_at"]
    assert str(tmp_path) not in provenance_text
    assert (run_dir / "scenario.yaml").read_text(encoding="utf-8") == (MINIMAL_EXPERIMENT_YAML)
    assert (run_dir / "summary.json").is_file()
    assert (run_dir / "errors.json").is_file()


def test_experiment_worker_failure_records_error_and_keeps_artifacts(tmp_path) -> None:
    """A failed run stays on disk with its status, message, and partial files."""
    gateway = FakeExperimentGateway(run_error=RuntimeError("simulation exploded"))
    service = _experiment_service(tmp_path, gateway)

    run_id = service.start(_experiment_payload())
    status = _wait_for_experiment(service, run_id)

    assert status["status"] == "error"
    assert status["summary"] is None
    assert "simulation exploded" in status["errors"][0]
    run_dir = next((tmp_path / ".satgonetem" / "experiments").iterdir())
    provenance = json.loads((run_dir / "provenance.json").read_text(encoding="utf-8"))
    assert provenance["status"] == "error"
    assert json.loads((run_dir / "errors.json").read_text(encoding="utf-8"))
    assert (run_dir / "scenario.yaml").is_file()


def test_experiment_list_skips_symlinked_and_malformed_runs(tmp_path) -> None:
    """The catalog scanner ignores escapes and incomplete directories."""
    gateway = FakeExperimentGateway()
    service = _experiment_service(tmp_path, gateway)
    run_id = service.start(_experiment_payload())
    _wait_for_experiment(service, run_id)

    run_root = tmp_path / ".satgonetem" / "experiments"
    malformed = run_root / "exp-malformed"
    malformed.mkdir()
    (malformed / "provenance.json").write_text("not-json", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (run_root / "exp-outside").symlink_to(outside)

    listing = service.list_runs()

    assert [run["run_id"] for run in listing["runs"]] == [run_id]


def test_experiment_live_holds_the_network_operation_until_done(tmp_path) -> None:
    """A live run blocks project/network mutations for its whole duration."""
    gateway = BlockingExperimentGateway()
    service = _experiment_service(tmp_path, gateway)

    run_id = service.start(_experiment_payload("live"))
    assert service.topology.session.network_operation is True
    try:
        assert (
            service.topology.session.begin(
                "Blocked",
                operation="create",
            )
            is False
        )
    finally:
        gateway.release.set()

    assert _wait_for_experiment(service, run_id)["status"] == "done"
    assert service.topology.session.network_operation is False


def test_experiment_metrics_tails_valid_jsonl_samples(tmp_path) -> None:
    """Metrics parsing skips malformed lines and returns the requested tail."""
    gateway = FakeExperimentGateway()
    service = _experiment_service(tmp_path, gateway)
    run_id = service.start(_experiment_payload())
    _wait_for_experiment(service, run_id)

    run_dir = gateway.runs[0][1]
    (run_dir / "metrics.jsonl").write_text(
        '{"sim_time_s": 0.0}\nnot json\n[1, 2]\n\n{"sim_time_s": 1.0}\n{"sim_time_s": 2.0}\n',
        encoding="utf-8",
    )

    result = service.metrics(run_id, tail=2)

    assert result["ok"] is True
    assert result["run_id"] == run_id
    assert result["total"] == 3
    assert result["samples"] == [{"sim_time_s": 1.0}, {"sim_time_s": 2.0}]


def test_experiment_metrics_missing_file_is_empty(tmp_path) -> None:
    """A run without a metrics artifact reports zero samples."""
    gateway = FakeExperimentGateway()
    service = _experiment_service(tmp_path, gateway)
    run_id = service.start(_experiment_payload("dry_run"))
    _wait_for_experiment(service, run_id)

    result = service.metrics(run_id, tail=10)

    assert result == {"ok": True, "run_id": run_id, "total": 0, "samples": []}


def test_experiment_metrics_bounds_and_unknown_run(tmp_path) -> None:
    """Tail bounds are enforced in the service and unknown ids are 404."""
    gateway = FakeExperimentGateway()
    service = _experiment_service(tmp_path, gateway)
    run_id = service.start(_experiment_payload())
    _wait_for_experiment(service, run_id)

    with pytest.raises(ValueError):
        service.metrics(run_id, tail=0)
    with pytest.raises(ValueError):
        service.metrics(run_id, tail=2001)
    with pytest.raises(APIError) as error:
        service.metrics("exp-missing", tail=10)
    assert error.value.status_code == 404


def test_experiment_summary_strips_server_paths(tmp_path) -> None:
    """Run summaries never expose absolute server paths, in memory or on disk."""

    class PathSummaryGateway(FakeExperimentGateway):
        def run_scenario(self, path, run_dir, mode):
            self.runs.append((path, run_dir, mode))
            return {
                "summary": {
                    "run_dir": str(run_dir),
                    "flows": {"count": 1},
                },
                "errors": [],
            }

    gateway = PathSummaryGateway()
    service = _experiment_service(tmp_path, gateway)
    run_id = service.start(_experiment_payload())
    status = _wait_for_experiment(service, run_id)

    assert "run_dir" not in status["summary"]
    run_dir = gateway.runs[0][1]
    assert "run_dir" not in json.loads((run_dir / "summary.json").read_text())
    assert "run_dir" not in json.loads((run_dir / "provenance.json").read_text())

    reloaded = _experiment_service(tmp_path, FakeExperimentGateway())
    assert "run_dir" not in reloaded.status(run_id)["summary"]
