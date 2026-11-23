# 0016 — Bounded throughput matrix (C6 phase 2)

Status: accepted

## Context

The monitor shows live link usage, and the connectivity matrix measures loss/RTT
between ordered pairs. A throughput matrix requires running short iperf3 flows
between selected nodes; this injects traffic and is expensive, so it needs its
own bounded background job rather than the one-flow queue registry.

## Requirements

- `POST /api/traffic/matrix` accepts an optional node list, duration, and
  concurrency; defaults to the first addressable traffic nodes.
- Require a loaded project, running GoNetEm, and applied addressing/routing;
  otherwise 409/422 before a worker starts.
- Caps: at most 12 nodes (132 ordered pairs), duration 1–10 s, concurrency 1–4,
  two concurrent matrix jobs, one-hour terminal retention.
- Run iperf3 flows in a daemon worker with bounded concurrency, poll each job
  to terminal/timeout, and record per-pair throughput, status, and error.
- Return progress, nodes, pair counts, a node-indexed matrix, and flat results.
- Export results as JSON/CSV through the existing download envelope.
- Abort/error remaining pairs if the project generation changes; never crash
  the worker.
- New `/matrix` page: node selection, duration/concurrency, start, progress,
  N×N heatmap, table, and exports; warn that the run injects traffic.

## Acceptance criteria

- Starting with fewer than two nodes or more than 12 is 422.
- Containers stopped or addressing not applied is 409.
- A started job moves running → done, reports completed/total pairs, and has a
  matrix with null diagonal and finite/none cells.
- Individual pair failures are retained without failing the whole job.
- Capacity exhaustion is 429; unknown IDs are 404.
- CSV has one row per ordered pair; JSON preserves the node axes and results.
- The page renders the heatmap/table and progress from mocked APIs.

## Edge cases and error paths

- Default node selection caps at 12 rather than selecting the whole topology.
- Duplicate/unknown node names are rejected.
- A pair timing out is recorded as an error; later pairs continue.
- The project changing mid-run marks remaining pairs aborted and keeps
  completed results.
- Matrix jobs are not cancellable in phase 2 (core flow cancellation is
  limited); the UI states this.
- Traffic from the matrix perturbs the network; the UI warns explicitly.
- Retention/TTL bounds memory; no server-side persistence across restarts.

## Non-goals

- Cancellation of in-flight iperf3 pairs.
- Persistent matrix history or scheduling.
- Parallel matrices beyond two jobs.
- Replacing the loss/RTT connectivity matrix.

## Validation

- Fake-traffic service tests for matrix assembly, progress, pair errors,
  timeouts, generation changes, caps, and exports.
- API tests for start/status/export, preconditions, bounds, and capacity.
- Vitest for heatmap binning/formatting and matrix summaries.
- Playwright with mocked matrix APIs for the heatmap/table/export.
- Full pytest, Vitest, Playwright, Ruff, format, wheel build, and CI.
- Real-container matrix run remains opt-in/manual.
