"""API characterization tests for server-side experiment runs."""

import time

import pytest

pytestmark = pytest.mark.integration

MINIMAL_SCENARIO = """\
name: Api Experiment
duration_s: 5
tick_s: 1
shells:
  - identifier: LEO
    planes: 2
    satellites_per_plane: 2
"""


def _wait_for_run(client, run_id):
    status = None
    for _ in range(300):
        response = client.get(f"/api/experiments/{run_id}")
        assert response.status_code == 200, response.text
        status = response.json()
        if status["status"] != "running":
            return status
        time.sleep(0.01)
    raise AssertionError(f"run did not finish: {status}")


def test_experiments_start_empty(client) -> None:
    """The artifact catalog is empty before any run."""
    response = client.get("/api/experiments")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "runs": []}


def test_experiment_run_writes_and_lists_artifacts(client, services, monkeypatch) -> None:
    """A background experiment run produces persistent artifacts."""

    class FakeExperimentGateway:
        def validate_scenario(self, path):
            return {
                "name": "Api Experiment",
                "shells": 1,
                "ground_stations": 0,
                "traffic": 0,
                "events": 0,
                "connectivity": False,
                "duration_s": 5,
            }

        def run_scenario(self, path, run_dir, mode):
            (run_dir / "metrics.jsonl").write_text(
                '{"sim_time_s": 0.0, "links": []}\n{"sim_time_s": 1.0, "links": []}\n',
                encoding="utf-8",
            )
            return {
                "summary": {
                    "flows": {"count": 0},
                    "mode": mode,
                    "run_dir": str(run_dir),
                },
                "errors": [],
            }

        def core_version(self):
            return "0.3.2-test"

    services.experiments.gateway = FakeExperimentGateway()

    started = client.post(
        "/api/experiments",
        json={"scenario_yaml": MINIMAL_SCENARIO, "mode": "offline"},
    )
    assert started.status_code == 200, started.text
    run_id = started.json()["run_id"]

    run = _wait_for_run(client, run_id)
    assert run["status"] == "done", run
    assert run["name"] == "Api Experiment"
    assert run["summary"]["mode"] == "offline"
    assert "run_dir" not in run["summary"]
    assert "provenance.json" in run["artifacts"]
    assert "summary.json" in run["artifacts"]
    assert "scenario.yaml" in run["artifacts"]

    listing = client.get("/api/experiments").json()
    assert listing["runs"][0]["run_id"] == run_id

    artifact = client.get(f"/api/experiments/{run_id}/artifacts/summary.json")
    assert artifact.status_code == 200, artifact.text
    data = artifact.json()
    assert data["filename"] == "summary.json"
    assert '"mode": "offline"' in data["content"]


def test_experiment_rejects_invalid_scenario_yaml(client) -> None:
    """Invalid scenario YAML is a 422 before a worker starts."""
    response = client.post(
        "/api/experiments",
        json={"scenario_yaml": "name: [unterminated", "mode": "offline"},
    )

    assert response.status_code == 422


def test_experiment_live_requires_stopped_containers(client, services, monkeypatch) -> None:
    """A live run cannot start while GoNetEm containers are running."""
    monkeypatch.setattr(services.topology, "network_running", lambda: True)

    response = client.post(
        "/api/experiments",
        json={"scenario_yaml": MINIMAL_SCENARIO, "mode": "live"},
    )

    assert response.status_code == 409
    assert "container" in response.json()["error"].lower()


def test_experiment_unknown_run_and_artifact_are_404(client) -> None:
    """Unknown run ids and artifact names do not escape the run directory."""
    assert client.get("/api/experiments/missing").status_code == 404
    assert client.get("/api/experiments/missing/artifacts/summary.json").status_code == 404


def test_experiment_metrics_endpoint_tails_samples(client, services, settings) -> None:
    """Metrics are parsed from JSONL and only the requested tail is returned."""
    run_id = _start_fake_run(client, services)

    response = client.get(f"/api/experiments/{run_id}/metrics?tail=1")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["run_id"] == run_id
    assert payload["total"] == 2
    assert [sample["sim_time_s"] for sample in payload["samples"]] == [1.0]
    assert (settings.save_root / ".satgonetem" / "experiments" / run_id / "metrics.jsonl").is_file()


def test_experiment_metrics_tail_bounds_are_422(client, services) -> None:
    """Tail must stay within the bounded polling window."""
    run_id = _start_fake_run(client, services)

    assert client.get(f"/api/experiments/{run_id}/metrics?tail=0").status_code == 422
    assert client.get(f"/api/experiments/{run_id}/metrics?tail=2001").status_code == 422
    assert client.get("/api/experiments/missing/metrics").status_code == 404


def _start_fake_run(client, services) -> str:
    """Start one offline run backed by a deterministic fake gateway."""

    class FakeExperimentGateway:
        def validate_scenario(self, path):
            return {
                "name": "Metrics Experiment",
                "shells": 1,
                "ground_stations": 0,
                "traffic": 0,
                "events": 0,
                "connectivity": False,
                "duration_s": 5,
            }

        def run_scenario(self, path, run_dir, mode):
            (run_dir / "metrics.jsonl").write_text(
                '{"sim_time_s": 0.0, "links": []}\n{"sim_time_s": 1.0, "links": []}\n',
                encoding="utf-8",
            )
            return {"summary": {"flows": {"count": 0}}, "errors": []}

        def core_version(self):
            return "0.3.2-test"

    services.experiments.gateway = FakeExperimentGateway()
    started = client.post(
        "/api/experiments",
        json={"scenario_yaml": MINIMAL_SCENARIO, "mode": "offline"},
    )
    assert started.status_code == 200, started.text
    run_id = started.json()["run_id"]
    assert _wait_for_run(client, run_id)["status"] == "done"
    return run_id
