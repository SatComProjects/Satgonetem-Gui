# 0004 — Experiment run detail, live metrics, and comparison

Status: accepted

## Context

PR #37 added server-side scenario runs with a persistent artifact catalog.
The catalog is currently write-only: a finished run exposes artifact
downloads, but there is no in-page view of its metrics or report, no way to
watch a running run's samples, and no way to compare two runs.

`metrics.jsonl` is appended during a run, so a running run already has usable
telemetry. `summary.json` contains the aggregate values needed for a compare
table, but the core report also embeds an absolute `run_dir` path that the API
currently returns to the browser.

## Requirements

- Add `GET /api/experiments/{run_id}/metrics?tail=N` returning parsed JSONL
  samples (default 300, max 2000), the total sample count, and the run ID.
- Expose metrics for running and terminal runs. Dry runs return an empty list.
- Remove the absolute `run_dir` field from summaries written and read by the
  service; API responses must not disclose server filesystem paths.
- Add a run detail panel: name, status, mode, timestamps, summary metrics,
  live metric chart, report text, scenario YAML, and artifact actions.
- Poll a running run's metrics every two seconds and redraw the chart; stop
  polling when the run leaves `running`.
- Add multi-run comparison: select two to four terminal runs, compare summary
  values, overlay one metric series over simulation time, and diff each
  scenario against the first selected run.
- Keep the existing run list, start flow, and artifact downloads working.

## Acceptance criteria

- `GET /api/experiments/{run_id}/metrics?tail=1` returns `total` samples and
  the last sample; malformed JSONL lines are skipped; `tail=0` and
  `tail > 2000` are 422; an unknown run is 404.
- A run whose metrics file is missing returns `samples: []` and `total: 0`.
- `summary.json`, the run status, and the catalog never contain `run_dir`.
- Clicking Details opens the detail panel for running and completed runs.
- While the selected run is running, the sample count and chart advance
  without a page reload; the poll stops on completion.
- Selecting two runs enables Compare; selecting more than four is prevented
  with a visible message.
- The compare table reports mode, duration, samples, TX/RX averages and
  maxima, flows/errors, simulator errors, and connectivity counts when
  present.
- The compare chart plots the selected metric for each run over simulation
  time; the scenario diff highlights added and removed lines.
- Chart.js being unavailable degrades to a visible message, not a page error.
- All fetches handle `ApiError` with a user-visible message.

## Edge cases and error paths

- A run in `error` state still opens: summary may be null, errors are shown,
  and partial artifacts are listed.
- A dry run has an empty metrics file; the detail panel reports "no samples".
- Metrics fetches while a run transitions to terminal are allowed; the next
  poll observes the final state and stops.
- Selecting a run that is later removed from memory keeps working from disk;
  a vanished run produces a 404 message and clears its chart series.
- Compare requires at least two selections and rejects more than four before
  fetching.
- Scenario diff is line-based and bounded by the submitted YAML size (1 MB);
  it never renders unescaped content.
- Detail and compare panels are mutually exclusive in the viewport, and each
  closes cleanly, destroying its chart instance.

## Non-goals

- Cancelling an in-flight run (the core runner exposes no cancel API).
- Rendering markdown to HTML; the report is shown as escaped preformatted text.
- Server-side comparison endpoints or persisted saved comparisons.
- Time-series export of a comparison; run artifacts remain the export.
- Replacing the browser-local interactive traffic history.

## Validation

- API tests for metrics parsing, tail bounds, missing files, unknown runs, and
  summary sanitization.
- Service tests for JSONL tolerance, tail selection, and a summary containing
  an absolute path (parsing is server-side).
- Vitest for series aggregation, formatting, compare rows, and line diffing.
- Playwright for detail with mocked metrics, compare with two runs, diff
  rendering, and the four-run selection cap.
- Full pytest, Vitest, Playwright, Ruff, format, wheel build, and CI.

## Decisions and open questions

- Metrics get a dedicated endpoint rather than reusing the artifact route so
  live polling can request a bounded tail and receive parsed samples.
- Comparison is client-side: the list and metrics endpoints already carry
  everything needed, and no new persisted state is introduced.
- Chart.js is already loaded by `base.html`; no chart dependency is added.
- `run_dir` is stripped only at the top level because that is the only path
  the core report emits; nested values are treated as data.
