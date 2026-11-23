# 0014 — Traffic monitor (phase 1)

Status: accepted

## Context

The GUI can run one-shot traffic jobs and color World View links by usage, but
there is no continuous monitor: no per-link/per-node time series, no retained
sample buffer, and no export. The usage endpoint already returns per-link
throughput/utilization when GoNetEm is running; link delay/capacity and
configured loss/jitter are available from `/api/links`.

## Requirements

- New `/monitor` page polling `/api/links/usage`, `/api/links`, and
  `/api/status` every two seconds while the page is visible.
- Retain a client ring buffer of 300 samples keyed by simulation step/time;
  pause/resume and clear controls.
- Show per-link current throughput, utilization, capacity, delay, configured
  loss, and jitter; show per-node aggregates from incident links.
- Label configured metrics separately from measured usage; show a visible
  "containers stopped / usage unavailable" state with the endpoint note.
- Charts for total throughput (and utilization) over retained samples; do not
  break when Chart.js is unavailable.
- Export the retained series as CSV and JSON.
- Keep the existing traffic queue/results flow untouched.

## Acceptance criteria

- With usage available, the first poll renders the link table, node summary,
  and chart canvas; subsequent polls append samples (capped at 300).
- Pausing stops new samples; resuming continues; clearing empties the table,
  series, and chart.
- The summary reports step/time, sample count, active links, and total
  throughput.
- Nodes are aggregated in both directions and sorted by throughput.
- CSV has a stable header and one row per sample (or per link-sample as
  documented) and downloads via the JSON envelope pattern; JSON round-trips.
- When usage is unavailable, the note is shown and no fabricated zeros appear.
- A 404/no project shows the load-project message; other failures are visible.
- Chart.js absence shows a text fallback with the current totals.

## Edge cases and error paths

- Missing `value_bps`, capacity, delay, loss, or jitter defaults to 0/— without
  throwing.
- Samples with no links are retained (zero throughput) but not treated as an
  unavailable sample.
- Duplicate link keys combine rather than overwrite.
- Pausing during an in-flight poll discards the late sample.
- Page hide/navigation clears the interval; no timer leaks.
- Large link sets: table is scrollable; charts use retained samples only.
- Export filenames are deterministic (`traffic-monitor.csv/json`).

## Non-goals

- N×N throughput matrix jobs (phase 2).
- Continuous server-side ping/iperf probes (phase 3).
- Durable history, alerting, or Prometheus integration.
- Measuring loss/jitter from live traffic; configured values are labelled.

## Validation

- Vitest for sample aggregation, per-node rollups, ring caps, unavailable
  handling, and CSV/JSON serialization.
- Playwright with mocked usage/status/links for rendering, pause/resume, clear,
  unavailable state, and CSV download.
- Full pytest (page/static contracts), Vitest, Playwright, Ruff, format, wheel
  build, and CI.

## Decisions and open questions

- Phase 1 is client-side and ephemeral; experiment-run metrics remain the
  durable time-series record.
- One sample every two seconds bounds memory and matches the existing World
  usage poll.
- The monitor does not start/stop traffic; it observes link usage and links to
  the existing Traffic page.
