# 0005 — Coverage snapshot analytics

Status: accepted

## Context

World View draws an approximate footprint per satellite, but the GUI cannot
answer the basic constellation-design question: what fraction of the Earth is
covered at the current step, per shell, and which ground stations are inside a
satellite footprint? SatGoNetem v0.3.2 already exposes
`TopologyManager.get_coverage_percentage()` and the public
`coverage_percentage_fast()` helper; the adapter only needs to call them.

A fine grid over a large constellation is CPU-heavy and must not freeze the
event loop or run unbounded.

## Requirements

- Add `POST /api/analysis/coverage` with an elevation mask (0–90°, default 10),
  grid resolution (0.25–10°, default 1), and toggles for per-shell and
  per-ground-station results.
- Return overall coverage percentage, satellite count, sampled grid cells,
  current step and project generation, duration, and whether the response was
  cached.
- Return per-shell coverage using the public coverage helper, grouped by the
  core shell `identifier`; cap at 24 shells and flag truncation.
- Return per-ground-station best elevation, best satellite, and covered state;
  cap the computed station count so ground-station × satellite work stays
  bounded, and flag truncation.
- Cache successful snapshots by project generation, step, elevation, resolution,
  and toggles; keep at most 16 entries and never cross a project generation.
- Reject missing projects with 404, no satellites with 422, and grids whose
  satellite-cell work exceeds 100,000,000 (or 1,200,000 cells) with a 422 that
  asks for a coarser resolution.
- Run the blocking computation in the FastAPI threadpool; no background job is
  required for a single bounded snapshot.

## Acceptance criteria

- A valid request returns `{ok, coverage_percent, satellites, sampled_cells,
  elevation_deg, grid_resolution_deg, step, generation, duration_ms, cached,
  shells, ground_stations, shells_truncated, ground_stations_truncated}`.
- `elevation_deg` outside 0–90 and `grid_resolution_deg` outside 0.25–10 are 422
  at the schema boundary.
- A request with 100 satellites at 1° succeeds; the same request at 0.25° is
  422 because the estimated work exceeds the cap.
- A repeated request at the same generation/step/options returns `cached: true`
  without another adapter call; a different elevation or a new generation
  recomputes.
- Per-shell values are sorted by shell identifier and reflect each shell's
  satellites only.
- Per-ground-station results identify the highest-elevation satellite and mark
  coverage against the requested elevation mask.
- The response never includes absolute filesystem paths.
- The page renders loading, empty, success, error, and too-large states.

## Edge cases and error paths

- A project with no satellites returns 422 instead of a 0% result.
- A project with no ground stations returns an empty list, not an error.
- Ground stations or shells beyond the caps are omitted and flagged truncated.
- Satellites without a position are skipped for ground-station elevation but
  still counted in the satellite total.
- The snapshot is read while the simulation may be running; values are an
  instantaneous approximation and the response records the captured step.
- Adapter failures are logged and returned as a 500 envelope.
- Switching projects invalidates the cache through the generation key.

## Non-goals

- A geographic uncovered-region mask or image export (the core returns an
  aggregate percentage).
- Time-series coverage over a scenario; use experiment runs for that.
- Replacing the approximate World View footprint circles with exact rings.
- Scheduled or multi-host coverage jobs.

## Validation

- Adapter tests with fake satellites/stations and a monkeypatched coverage
  helper for overall, per-shell, elevation, and truncation behavior.
- Service tests for preconditions, work caps, caching, generation
  invalidation, and pass-through.
- API tests for the success envelope, schema bounds, no-project 404, and the
  too-large 422.
- Vitest for percentage/class formatting, station sorting, and result shaping.
- Playwright for the analyze flow, per-shell bars, ground-station table, and
  the error state.
- Full pytest, Vitest, Playwright, Ruff, format, wheel build, and CI.

## Decisions and open questions

- Coverage is a dedicated `/coverage` page rather than a World View card, so it
  works without WebGL and keeps the globe page focused.
- The core API returns only a percentage, so the `uncovered region` is
  represented by uncovered ground stations and the inverse percentage, not a
  geographic mask.
- The work cap is derived from a measured ~170M satellite-cells/s; 100M keeps a
  worst-case request near one second before per-shell duplication.
