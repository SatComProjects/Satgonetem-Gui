# 0002 — Full-mesh connectivity matrix

Status: accepted

## Context

SatGoNetEm v0.3.2 provides a typed `build_connectivity_matrix()` that pings
every ordered pair and returns loss/RTT results. The GUI can run individual
traffic jobs, but verifying an N-node topology requires manual runs and
copying results.

A full mesh can be expensive and long-running, so it must not block the ASGI
event loop and must be bounded.

## Requirements

- Start a background matrix job over addressable ground stations and satellites.
- Require a loaded project, running GoNetEm containers, and applied addressing
  and routing.
- Allow an explicit node subset or default to all addressable endpoints.
- Cap runs at 32 nodes and 2,000 ordered pairs; cap concurrent jobs at four.
- Report running/done/error state, node axes, pair summary, per-pair loss/RTT,
  timestamps, and elapsed time.
- Export complete results as CSV and JSON.
- Use the public v0.3.2 matrix API; no hand-written ping loops.

## Acceptance criteria

- `POST /api/diagnostics/connectivity` returns a job ID.
- `GET /api/diagnostics/connectivity/{id}` returns the job snapshot.
- `GET /api/diagnostics/connectivity/{id}/export?format=csv|json` returns a
  JSON download envelope with filename/content/content type.
- The page renders an N×N heatmap with loss buckets, RTT text, unreachable
  cells, and a legend.
- Export controls only appear for completed jobs.
- Unknown IDs are 404; invalid/too-large selections are 422; missing
  containers/addressing are 409; capacity exhaustion is 429.

## Edge cases and error paths

- A project change during a run marks the job failed rather than mixing
  generations.
- A core matrix failure is a job error; the thread never crashes the server.
- Jobs are bounded, terminal transitions immutable, and terminal jobs expire
  after one hour.
- The heatmap scrolls inside its card for large matrices; removed jobs require
  a new run.
- Addressability is session-scoped for Walker projects; only addressable
  satellites are candidates.
- A topology with fewer than two addressable endpoints returns 422.

## Non-goals

- Cancellation of an in-flight matrix (FlowScheduler has no public cancel).
- Persisting matrix jobs across restarts; exports are the durable artifact.
- Per-pair time-series or scheduled repeats.
- Multi-host concurrency or authentication.

## Validation

- Service tests with a fake controller for preconditions, caps, jobs, errors,
  generation changes, TTL, and exports.
- Adapter tests with a monkeypatched core matrix builder.
- API tests for start/status/export and no-project/container preconditions.
- Vitest for loss buckets, summaries, and pair counts.
- Playwright for page start, heatmap, and CSV download.
- Full pytest, Vitest, Playwright, Ruff, format, and wheel build.

## Decisions and open questions

- The matrix runs in a daemon worker thread; the API only creates/schedules it.
- JSON export preserves the node axes; CSV has one row per ordered pair.
- At most 32 nodes keeps the heatmap and the underlying ping storm bounded.
