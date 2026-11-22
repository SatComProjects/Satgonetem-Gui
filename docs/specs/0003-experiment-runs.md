# 0003 — Server-side experiment runs and artifacts

Status: accepted

## Context

SatGoNetEm v0.3.2 ships a declarative `Scenario` format and `ExperimentRunner`
with telemetry (`MetricsCollector`, JSONL writers, report generation). The GUI
currently persists only compact browser-local traffic history; it cannot run a
scenario or retain server-side manifests, metrics, and reports.

## Requirements

- Accept a scenario YAML document and run it in one of three modes:
  `dry_run` (validate/write manifest), `offline` (build/sample without
  containers), or `live` (start GoNetEm, events, traffic, then stop).
- Validate with the core `Scenario` parser before starting a worker.
- Store each run under `SATGONETEM_GUI_SAVE_ROOT/.satgonetem/experiments/` with
  `scenario.yaml`, `manifest.yaml`, `metrics.jsonl`, `flows.json`,
  `errors.json`, `summary.json`, `report.md`, optional `connectivity.json`, and
  `provenance.json`.
- Record provenance: GUI version, core version, run ID, scenario name and hash,
  mode, timestamps, and status. Do not expose absolute paths or environment
  dumps in API responses.
- List runs, show status/summary/errors, and download allowlisted artifacts.
- Bound concurrent runs (2) and live runs (1); live mode requires stopped
  GoNetEm containers.
- Keep artifacts after failures for diagnosis.

## Acceptance criteria

- `POST /api/experiments` with a valid scenario returns a run ID.
- Invalid scenario YAML is 422 and does not leave a run directory.
- `GET /api/experiments` lists runs newest first; `GET /api/experiments/{id}`
  returns status and summary.
- `GET /api/experiments/{id}/artifacts/{name}` returns JSON download content for
  allowlisted names only; traversal/unknown names are 404.
- Live mode returns 409 while containers are running or another live run is
  active.
- A failed worker writes errors/provenance and transitions to `error`.
- Dry/offline modes work without Docker; live mode is not exercised by the
  default suite.

## Edge cases and error paths

- Scenario parsing/building errors are captured as run errors or a 422 when
  validation fails before starting.
- Runner artifacts are partial on failure; listing tolerates missing files.
- Run IDs are opaque and directory names are generated server-side.
- Concurrent live runs are rejected; terminal jobs expire from memory after an
  hour but artifacts remain on disk.
- A scenario with a `topology` path is resolved by the core runner; the GUI does
  not read arbitrary client paths itself.
- Artifact downloads use the existing JSON envelope rather than a raw file
  route, preserving the `/api/` OpenAPI contract.

## Non-goals

- Editing scenario fields in a visual builder.
- Cancelling an in-flight ExperimentRunner.
- Replacing the browser-local interactive traffic queue/history in this slice.
- Multi-user sharing or authentication.
- Running arbitrary commands or serving unlisted files.

## Validation

- Adapter tests with a real minimal scenario and an injected fake runner for
  mode flags.
- Service/API tests with a fake gateway for start/status/list/artifact,
  invalid YAML, live guards, and containment.
- Vitest for status/artifact/summary formatting.
- Playwright for start, run list, and artifact download with mocked APIs.
- Full pytest, Vitest, Playwright, Ruff, format, and wheel build.

## Decisions and open questions

- The service writes provenance and summary even if the core runner fails, so
  every run has a diagnosable record.
- `dry_run` is the safest default for validation; the UI defaults to `offline`
  to produce metrics without starting containers.
- Interactive traffic history remains client-side; scenario artifacts are the
  server-backed experiment record.
