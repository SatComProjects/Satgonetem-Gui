"""Server-side experiment run orchestration and artifact catalog."""

import hashlib
import importlib.metadata
import json
import logging
import os
import secrets
import shutil
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ..config import Settings
from ..errors import APIError
from ..schemas import ExperimentStartRequest
from ..storage import write_text_atomic
from ..time_utils import utc_timestamp
from .ports import ExperimentGateway
from .topology_service import TopologyService

logger = logging.getLogger(__name__)

MAX_CONCURRENT_RUNS = 2
MAX_LIVE_RUNS = 1
TERMINAL_TTL_SECONDS = 3600.0
RUN_ID_PREFIX = "exp-"
MAX_METRICS_TAIL = 2000
DEFAULT_METRICS_TAIL = 300

# Artifact filenames the API may expose. The catalog and the artifact route
# both use this allowlist so a run directory can never be browsed arbitrarily.
ARTIFACT_NAMES = (
    "scenario.yaml",
    "manifest.yaml",
    "summary.json",
    "report.md",
    "metrics.jsonl",
    "flows.json",
    "errors.json",
    "connectivity.json",
    "provenance.json",
)
_CONTENT_TYPES = {
    ".yaml": "text/yaml",
    ".json": "application/json",
    ".md": "text/markdown",
    ".jsonl": "application/x-ndjson",
}
_RUN_MODES = frozenset({"dry_run", "offline", "live"})
_RUN_STATUSES = frozenset({"running", "done", "error"})
_SCENARIO_FILENAME = "scenario.yaml"


def _is_within(path: Path, root: Path) -> bool:
    """Return whether ``path`` is at or below ``root``."""
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _gui_version() -> str:
    """Return the installed GUI package version."""
    try:
        return importlib.metadata.version("satgonetem-gui")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


@dataclass
class ExperimentRunJob:
    """One running or finished experiment run held in memory."""

    run_id: str
    name: str
    mode: str
    scenario_path: Path
    run_dir: Path
    status: str = "running"
    started_at: str = field(default_factory=utc_timestamp)
    finished_at: str | None = None
    summary: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)
    holds_network: bool = False
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    _terminal: threading.Event = field(
        default_factory=threading.Event,
        repr=False,
        compare=False,
    )

    @property
    def terminal(self) -> bool:
        """Return True once the job reached a terminal state."""
        return self._terminal.is_set()


class ExperimentService:
    """Validate, run, and catalog declarative experiment scenarios."""

    def __init__(
        self,
        settings: Settings,
        topology: TopologyService,
        gateway: ExperimentGateway,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.settings = settings
        self.topology = topology
        self.gateway = gateway
        self._clock = clock
        self._save_root = Path(settings.save_root).expanduser().resolve()
        run_root = (self._save_root / ".satgonetem" / "experiments").resolve()
        if not _is_within(run_root, self._save_root):
            raise ValueError("Experiment run root must be inside the save root.")
        self._run_root = run_root
        self._jobs: dict[str, ExperimentRunJob] = {}
        self._pending_runs = 0
        self._pending_live = 0
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    def start(self, payload: ExperimentStartRequest) -> str:
        """Validate a submitted scenario and launch one background run."""
        if payload.mode == "live" and self.topology.network_running():
            raise APIError(
                409,
                "Stop GoNetEm containers before a live experiment.",
            )

        self._reserve(payload.mode)

        network_reserved = False
        try:
            if payload.mode == "live":
                session = getattr(self.topology, "session", None)
                begin_network = getattr(session, "begin_network_operation", None)
                if callable(begin_network):
                    if not begin_network():
                        raise APIError(
                            409,
                            "A project or network operation is already running.",
                        )
                    network_reserved = True
        except Exception:
            if network_reserved:
                self.topology.session.end_network_operation()
            self._release(payload.mode)
            raise

        committed = False
        run_dir: Path | None = None
        try:
            run_id, run_dir = self._create_run_dir()
            scenario_path = run_dir / _SCENARIO_FILENAME
            write_text_atomic(scenario_path, payload.scenario_yaml)
            details = self.gateway.validate_scenario(scenario_path)
            if not isinstance(details, dict):
                raise ValueError("Experiment validation returned an invalid result.")

            job = ExperimentRunJob(
                run_id=run_id,
                name=self._scenario_name(details),
                mode=payload.mode,
                scenario_path=scenario_path,
                run_dir=run_dir,
                holds_network=network_reserved,
                created_at=self._clock(),
                updated_at=self._clock(),
            )
            self._commit(job, payload.mode)
            committed = True
        except ValueError as exc:
            self._discard_run_dir(run_dir)
            message = str(exc).strip() or "Invalid experiment scenario."
            raise APIError(422, message) from exc
        except APIError:
            self._discard_run_dir(run_dir)
            raise
        except Exception as exc:
            logger.exception("Failed to start an experiment run.")
            self._discard_run_dir(run_dir)
            raise APIError(500, "Failed to start experiment run.") from exc
        finally:
            if not committed:
                if network_reserved:
                    self.topology.session.end_network_operation()
                self._release(payload.mode)

        thread = threading.Thread(
            target=self._worker,
            args=(job,),
            name=f"experiment-{job.run_id}",
            daemon=True,
        )
        try:
            thread.start()
        except Exception as exc:
            logger.exception("Could not start the experiment worker thread.")
            self._finalize_job(
                job,
                "error",
                None,
                ["Failed to start experiment worker."],
            )
            raise APIError(500, "Failed to start experiment run.") from exc
        return job.run_id

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def list_runs(self) -> dict[str, Any]:
        """Return the newest-first experiment catalog from disk and memory."""
        self._prune()
        entries: dict[str, dict[str, Any]] = {}
        for entry in self._scan_disk_runs():
            entries[entry["run_id"]] = entry

        with self._lock:
            running = [job for job in self._jobs.values() if not job.terminal]
            running_entries = [self._job_entry(job) for job in running]
        for entry in running_entries:
            entries[entry["run_id"]] = entry

        ordered = sorted(
            entries.values(),
            key=lambda entry: (entry["started_at"], entry["run_id"]),
            reverse=True,
        )
        return {"ok": True, "runs": ordered}

    def status(self, run_id: str) -> dict[str, Any]:
        """Return one run's current state, from memory or completed disk data."""
        self._prune()
        with self._lock:
            job = self._jobs.get(run_id)
            if job is not None:
                return self._job_entry(job)

        run_dir = self._resolve_run_dir(run_id)
        entry = self._disk_entry(run_id, run_dir) if run_dir is not None else None
        if entry is None:
            raise APIError(404, "Experiment run not found.")
        return entry

    def artifact(self, run_id: str, name: str) -> dict[str, Any]:
        """Return one allowlisted artifact's text content."""
        if name not in ARTIFACT_NAMES:
            raise APIError(404, "Experiment artifact not found.")
        run_dir = self._resolve_run_dir(run_id)
        if run_dir is None:
            raise APIError(404, "Experiment run not found.")

        target = run_dir / name
        try:
            resolved = target.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise APIError(404, "Experiment artifact not found.") from exc
        if resolved.parent != run_dir or not resolved.is_file():
            raise APIError(404, "Experiment artifact not found.")
        try:
            content = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise APIError(404, "Experiment artifact not found.") from exc

        return {
            "ok": True,
            "filename": name,
            "content": content,
            "content_type": _CONTENT_TYPES.get(resolved.suffix.lower(), "application/octet-stream"),
        }

    def metrics(self, run_id: str, tail: int = DEFAULT_METRICS_TAIL) -> dict[str, Any]:
        """Return the newest parsed metric samples for one run."""
        if tail < 1 or tail > MAX_METRICS_TAIL:
            raise ValueError(f"Metrics tail must be between 1 and {MAX_METRICS_TAIL}.")

        run_dir = self._resolve_run_dir(run_id)
        if run_dir is None:
            raise APIError(404, "Experiment run not found.")

        # Dry runs have no usable metrics file; report an empty tail instead.
        try:
            content = (run_dir / "metrics.jsonl").read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            content = ""

        samples: list[dict[str, Any]] = []
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                sample = json.loads(stripped)
            except ValueError:
                continue
            if isinstance(sample, dict):
                samples.append(sample)

        return {
            "ok": True,
            "run_id": run_id,
            "total": len(samples),
            "samples": samples[-tail:],
        }

    # ------------------------------------------------------------------
    # Registry
    # ------------------------------------------------------------------

    def _reserve(self, mode: str) -> None:
        """Reserve a run slot before file or validation work begins."""
        with self._lock:
            self._prune_locked(self._clock())
            running = [job for job in self._jobs.values() if not job.terminal]
            if mode == "live":
                live_count = self._pending_live + sum(1 for job in running if job.mode == "live")
                if live_count >= MAX_LIVE_RUNS:
                    raise APIError(
                        409,
                        "A live experiment is already running.",
                    )
            if len(running) + self._pending_runs >= MAX_CONCURRENT_RUNS:
                raise APIError(
                    429,
                    "Experiment run limit reached. Wait for a running run to finish.",
                )
            self._pending_runs += 1
            if mode == "live":
                self._pending_live += 1

    def _release(self, mode: str) -> None:
        """Release a reserved slot that never turned into a job."""
        with self._lock:
            self._pending_runs = max(0, self._pending_runs - 1)
            if mode == "live":
                self._pending_live = max(0, self._pending_live - 1)

    def _commit(self, job: ExperimentRunJob, mode: str) -> None:
        """Promote a reservation into a running job."""
        with self._lock:
            self._pending_runs = max(0, self._pending_runs - 1)
            if mode == "live":
                self._pending_live = max(0, self._pending_live - 1)
            self._jobs[job.run_id] = job

    def _prune(self) -> None:
        """Drop terminal jobs older than the in-memory TTL."""
        with self._lock:
            self._prune_locked(self._clock())

    def _prune_locked(self, now: float) -> None:
        expired = [
            run_id
            for run_id, job in self._jobs.items()
            if job.terminal and now - job.updated_at >= TERMINAL_TTL_SECONDS
        ]
        for run_id in expired:
            del self._jobs[run_id]

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------

    def _worker(self, job: ExperimentRunJob) -> None:
        """Drive one run and always leave a terminal state behind."""
        try:
            self._execute(job)
        except BaseException:  # noqa: BLE001 - the worker must not die silently
            logger.exception("Experiment run %s crashed.", job.run_id)
            self._finalize_job(
                job,
                "error",
                None,
                ["Experiment runner stopped unexpectedly."],
            )

    def _execute(self, job: ExperimentRunJob) -> None:
        """Run the scenario and persist summary, errors, and provenance."""
        summary: dict[str, Any] | None = None
        errors: list[str] = []
        status = "error"
        try:
            result = self.gateway.run_scenario(
                job.scenario_path,
                job.run_dir,
                job.mode,
            )
            if not isinstance(result, dict):
                raise RuntimeError("Experiment gateway returned an invalid result.")
            raw_summary = result.get("summary")
            raw_errors = result.get("errors") or []
            summary = self._sanitize_summary(raw_summary)
            if summary is None:
                raise RuntimeError("Experiment gateway returned an invalid summary.")
            if not isinstance(raw_errors, list):
                raw_errors = [str(raw_errors)]
            errors = [str(error) for error in raw_errors]
            self._write_json(job.run_dir / "summary.json", summary)
            self._write_json(job.run_dir / "errors.json", errors)
            status = "done"
        except Exception as exc:
            logger.exception("Experiment run %s failed.", job.run_id)
            summary = None
            errors = [
                str(exc).strip()[:500] or "Experiment run failed.",
            ]
            try:
                self._write_json(job.run_dir / "errors.json", errors)
            except Exception:  # noqa: BLE001 - diagnostics must not hide the failure
                logger.exception(
                    "Could not write errors.json for experiment %s.",
                    job.run_id,
                )

        self._finalize_job(job, status, summary, errors)

    def _finalize_job(
        self,
        job: ExperimentRunJob,
        status: str,
        summary: dict[str, Any] | None,
        errors: list[str],
    ) -> None:
        """Write provenance and move the in-memory job to a terminal state."""
        finished_at = utc_timestamp()
        try:
            self._write_provenance(job, status, finished_at)
        except Exception:  # noqa: BLE001 - a failed metadata write is reported
            logger.exception(
                "Could not write provenance.json for experiment %s.",
                job.run_id,
            )

        with self._lock:
            if job.terminal:
                return
            job.status = status
            job.summary = summary
            job.errors = list(errors)
            job.finished_at = finished_at
            job.updated_at = self._clock()
            job._terminal.set()
            release_network = job.holds_network
            job.holds_network = False
        if release_network:
            self.topology.session.end_network_operation()

    # ------------------------------------------------------------------
    # Artifacts and catalog
    # ------------------------------------------------------------------

    def _write_provenance(
        self,
        job: ExperimentRunJob,
        status: str,
        finished_at: str,
    ) -> None:
        """Persist run metadata without absolute paths or environment data."""
        try:
            digest = hashlib.sha256(job.scenario_path.read_bytes()).hexdigest()
        except OSError:
            digest = ""
        try:
            core_version = self.gateway.core_version()
        except Exception:  # noqa: BLE001 - provenance stays best-effort
            logger.exception("Could not read the SatGoNetem core version.")
            core_version = "unknown"

        payload = {
            "gui_version": _gui_version(),
            "core_version": core_version,
            "run_id": job.run_id,
            "name": job.name,
            "mode": job.mode,
            "scenario_filename": _SCENARIO_FILENAME,
            "scenario_sha256": digest,
            "started_at": job.started_at,
            "finished_at": finished_at,
            "status": status,
        }
        self._write_json(job.run_dir / "provenance.json", payload)

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        """Write one JSON artifact atomically."""
        write_text_atomic(path, json.dumps(payload, indent=2) + "\n")

    def _scan_disk_runs(self) -> list[dict[str, Any]]:
        """Safely scan the run root for completed runs."""
        if not self._run_root.is_dir():
            return []
        try:
            entries = list(os.scandir(self._run_root))
        except OSError:
            return []

        runs: list[dict[str, Any]] = []
        for entry in entries:
            try:
                if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            run_id = entry.name
            run_dir = self._resolve_run_dir(run_id)
            if run_dir is None:
                continue
            record = self._disk_entry(run_id, run_dir)
            if record is not None:
                runs.append(record)
        return runs

    def _disk_entry(
        self,
        run_id: str,
        run_dir: Path,
    ) -> dict[str, Any] | None:
        """Build one catalog entry from persisted artifacts."""
        provenance = self._read_json(run_dir / "provenance.json")
        if not isinstance(provenance, dict):
            return None
        name = provenance.get("name")
        started_at = provenance.get("started_at")
        mode = provenance.get("mode")
        status = provenance.get("status")
        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(started_at, str)
            or mode not in _RUN_MODES
            or status not in _RUN_STATUSES
        ):
            return None

        finished = provenance.get("finished_at")
        summary = self._sanitize_summary(self._read_json(run_dir / "summary.json"))
        errors = self._read_json(run_dir / "errors.json")
        return {
            "run_id": run_id,
            "name": name,
            "mode": mode,
            "status": status,
            "started_at": started_at,
            "finished_at": finished if isinstance(finished, str) else None,
            "summary": summary,
            "errors": ([str(error) for error in errors] if isinstance(errors, list) else []),
            "artifacts": self._artifacts_for(run_dir),
        }

    def _job_entry(self, job: ExperimentRunJob) -> dict[str, Any]:
        """Build a catalog-shaped entry from an in-memory job."""
        with self._lock:
            record = {
                "run_id": job.run_id,
                "name": job.name,
                "mode": job.mode,
                "status": job.status,
                "started_at": job.started_at,
                "finished_at": job.finished_at,
                "summary": self._sanitize_summary(job.summary),
                "errors": list(job.errors),
                "artifacts": [],
            }
        record["artifacts"] = self._artifacts_for(job.run_dir)
        return record

    @staticmethod
    def _sanitize_summary(summary: Any) -> dict[str, Any] | None:
        """Return a summary copy without the server-side run directory path."""
        if not isinstance(summary, dict):
            return None
        return {key: value for key, value in summary.items() if key != "run_dir"}

    @staticmethod
    def _artifacts_for(run_dir: Path) -> list[str]:
        """Return allowlisted artifacts that exist in one run directory."""
        artifacts: list[str] = []
        for name in ARTIFACT_NAMES:
            candidate = run_dir / name
            try:
                if candidate.is_file() and not candidate.is_symlink():
                    artifacts.append(name)
            except OSError:
                continue
        return artifacts

    @staticmethod
    def _read_json(path: Path) -> Any:
        """Read JSON, returning None for missing or malformed files."""
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def _resolve_run_dir(self, run_id: str) -> Path | None:
        """Resolve a run id to a contained directory, rejecting escapes."""
        if not isinstance(run_id, str) or not run_id.startswith(RUN_ID_PREFIX):
            return None
        if "/" in run_id or "\\" in run_id or run_id in {".", ".."}:
            return None
        if any(part.startswith(".") for part in Path(run_id).parts):
            return None
        candidate = self._run_root / run_id
        try:
            if candidate.is_symlink():
                return None
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            return None
        if not _is_within(resolved, self._run_root) or not resolved.is_dir():
            return None
        return resolved

    def _create_run_dir(self) -> tuple[str, Path]:
        """Create a unique, timestamped run directory under the run root."""
        self._run_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        for _ in range(8):
            run_id = f"{RUN_ID_PREFIX}{stamp}-{secrets.token_hex(4)}"
            run_dir = self._run_root / run_id
            try:
                run_dir.mkdir()
            except FileExistsError:
                continue
            return run_id, run_dir
        raise RuntimeError("Could not allocate an experiment run directory.")

    def _discard_run_dir(self, run_dir: Path | None) -> None:
        """Remove a failed start's contained run directory."""
        if run_dir is None:
            return
        try:
            resolved = run_dir.resolve()
        except (OSError, RuntimeError):
            return
        if _is_within(resolved, self._run_root):
            shutil.rmtree(resolved, ignore_errors=True)

    @staticmethod
    def _scenario_name(details: dict[str, Any]) -> str:
        """Return the validated scenario name with a safe fallback."""
        name = details.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
        return "Experiment"
