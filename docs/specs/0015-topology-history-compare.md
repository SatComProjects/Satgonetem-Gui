# 0015 — Topology history and timestamp comparison (B6 phase 2)

Status: accepted

## Context

The phase-1 topology graph shows one snapshot. Comparing two simulation steps
requires retaining observed link/node states; seeking the live simulation with
`move_to_time` to reconstruct history would disturb the user's session. The
service therefore records only steps the GUI has observed.

## Requirements

- Record the current step on demand and after each graph poll; repeated polls
  at the same step are no-ops.
- Keep a bounded in-memory ring: 240 snapshots and 100,000 link records; clear
  on project generation change.
- Store node identity/type/city/shell and link endpoints/type/delay/capacity/
  loss/jitter/active state per snapshot.
- `POST /api/topology/snapshots` records; `GET /api/topology/snapshots` lists
  summaries oldest-first; `GET /api/topology/compare?from_step=&to_step=`
  returns added/removed/changed links and added/removed nodes.
- Unknown compare steps are 404; the list works without a project (empty).
- The topology page records automatically, lists snapshot counts, selects two
  steps, renders a diff table, and highlights added/removed/changed links.
  Removed links are drawn as red ghost edges when their endpoints are still
  visible; otherwise they remain in the table.
- No seek/mutation of the live simulation.

## Acceptance criteria

- Recording step 0 twice returns `recorded: false` the second time and lists
  one snapshot.
- After advancing the step and changing/adding links, compare reports the
  expected added/removed/changed sets and node changes.
- The ring keeps the newest 240 snapshots and evicts oldest records under the
  link budget.
- A generation change clears prior snapshots.
- UI compare selects show recorded steps, the summary counts match, and graph
  edges get `added`/`removed`/`changed` classes.
- Without a project, recording is 404, listing is an empty 200, and compare is
  404.

## Edge cases and error paths

- Same-step changes are not recorded until the step advances; this is explicit
  and avoids ambiguous duplicate steps.
- Missing/partial link fields default safely in stored records.
- A removed link whose endpoint disappeared is table-only.
- Compare errors clear graph diff classes.
- Snapshot records contain no absolute paths or request payloads.
- Recording is bounded and synchronous; no background thread.

## Non-goals

- Reconstructing arbitrary unobserved steps or seeking the simulation.
- Durable snapshot storage across restarts.
- Traffic/flow diffs; only topology links/nodes.
- Automatic snapshot export.

## Validation

- Service tests for dedupe, ring caps, generation clears, added/removed/changed
  links, unchanged comparisons, and unknown steps.
- API tests for record/list/compare and no-project behavior.
- Playwright for automatic recording, compare controls, diff table, and edge
  classes.
- Full pytest, Vitest, Playwright, Ruff, format, wheel build, and CI.

## Decisions and open questions

- History is observed-only and in-memory; experiment artifacts remain the
  durable record.
- Recording piggybacks on the graph's five-second poll with step deduplication.
- Link changes are compared by unordered endpoint key; endpoints are displayed
  in their recorded orientation.
