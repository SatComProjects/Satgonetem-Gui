# 0006 — Topology export and graph health

Status: accepted

## Context

The Nodes page and connectivity matrix show topology data, but there is no way
to export the graph for external analysis or to spot structural problems such
as isolated nodes, duplicate coordinates, or zero-capacity links. The core
builds links keyed by an unordered node pair and treats them as bidirectional,
so a directed asymmetry check would be a false positive.

## Requirements

- Add `GET /api/topology/health` returning node/link counts and deterministic
  checks: isolated nodes, incomplete positions, duplicate positions, zero or
  negative capacity, negative delay, self-links, and duplicate link pairs.
- Add `GET /api/topology/export?format=json|dot|graphml` returning the existing
  JSON download envelope (`ok`, `filename`, `content`, `content_type`).
- JSON exports include a schema tag, nodes, and links. DOT exports a
  `graph topology` with node/edge attributes. GraphML exports an undirected
  graph with typed keys.
- Mark isolated nodes as informational (a ground station out of view is
  normal); mark the other findings as warnings. `healthy` is true when no
  warning check has a positive count.
- Cap check item lists at 20 while reporting the full count.
- Reject exports over 10,000,000 characters with a 422 envelope.
- Keep serialization and health analysis in pure modules; the adapter/service
  only fetches topology data and shapes the response.

## Acceptance criteria

- Without a project both endpoints are 404.
- `health` reports `nodes`, `links`, `healthy`, and every check ID with a
  severity, message, count, and bounded items.
- A topology with only isolated nodes still returns 200 with an empty link list
  and an informational isolated-node check.
- `export?format=json` parses as JSON with the schema tag and every node/link.
- `export?format=dot` starts with `graph topology {` and contains quoted node
  IDs; `export?format=graphml` contains `<graphml` and a node element.
- An invalid format is 422 at the query boundary.
- The Nodes page shows a health card, severity badges, item previews, and
  JSON/DOT/GraphML download buttons; failures are visible and actionable.

## Edge cases and error paths

- Missing latitude, longitude, or altitude marks a node as incomplete and
  excludes it from duplicate-position grouping.
- Duplicate positions compare rounded values (6 decimals latitude/longitude,
  3 decimals altitude) to avoid floating noise.
- Warnings do not hide informational checks; the UI lists every non-empty
  check.
- Export content escapes quotes/backslashes for DOT and XML entities for
  GraphML; node names with markup cannot break the document.
- No project, empty topology, and a project with no links are distinct states.
- Export caps protect the response envelope; no streaming is introduced.

## Non-goals

- Persisting exports server-side or scheduling them.
- Graph layout, image rendering, or PDF reports.
- Directed/asymmetric link checks (the core model is bidirectional).
- Changing the topology or repairing findings.

## Validation

- Pure unit tests for each health check, healthy/unhealthy aggregation, item
  caps, and empty inputs.
- Serializer unit tests for JSON shape, DOT quoting, GraphML escaping, and
  content types.
- API tests with the real fixture topology for health and all three formats,
  plus no-project and invalid-format cases.
- Vitest for summary/severity formatting and non-empty check filtering.
- Playwright for the health card and a downloaded export.
- Full pytest, Vitest, Playwright, Ruff, format, wheel build, and CI.

## Decisions and open questions

- The endpoints live at `/api/topology/...`, not under `/api/analysis`, because
  they are reads of the topology graph rather than computed analysis.
- Exports are synchronous; the default fixture topology is small and the
  10 MB cap bounds the envelope.
- Isolated nodes are informational so a normal out-of-view ground station does
  not mark a project unhealthy.
