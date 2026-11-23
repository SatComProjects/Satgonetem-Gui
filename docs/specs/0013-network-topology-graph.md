# 0013 — Network topology graph (phase 1)

Status: accepted

## Context

World View is orbital, Node Explorer is a list, and the topology endpoints
return nodes/links but no whole-network picture. The catalogue's B6 phase 1
calls for a dedicated, deterministic 2D graph with edge metrics, partitions,
path highlighting, and an inspector. Phase 2 (recorded timestamp comparison)
is specified separately.

The current payloads lack two fields the graph needs: satellite shell
identifiers and link loss/jitter. Both are available in the core/fixture data
and are pin-safe additions.

## Requirements

- New `/topology` page with a deterministic SVG graph, no force simulation and
  no new frontend dependency.
- Distinct satellite/ground-station markers; edges by type/state with
  delay/capacity/loss/jitter in the accessible title and a side legend.
- Filters for shell, node type, and name/city/shell search; shell filtering
  applies to satellites while ground stations remain for context.
- Node selection opens an inspector using `/api/nodes/{name}` (interfaces,
  addresses, routing table); close returns the graph to normal.
- Two node selects and a trace action highlight the route using
  `/api/routing/path`.
- Connected-component partitions are computed in a pure module, counted in the
  UI, and colorable with a "Highlight partitions" toggle.
- Cap rendered nodes/edges (1,500 / 5,000) with a visible overflow message.
- Show loading, empty, no-project, and fetch-error states; preserve filters and
  selection across the five-second poll.
- Backend: expose satellite `shell` on `/api/satellites` and `/api/nodes`
  (mapping from the simulation manager's object ids, falling back to the
  topology satellite's shell); expose `loss_percent` and `jitter_ms` on
  `/api/links`.

## Acceptance criteria

- The default fixture graph renders 101 nodes and its links; satellites and
  ground stations have distinct classes.
- Shell options include `LEO`; selecting it keeps satellites of that shell and
  the ground station; type/search filters compose.
- Hidden endpoints remove their links.
- The layout is deterministic for shuffled input and stays inside the viewBox.
- Partition count is correct for disconnected fixtures; toggling highlight
  colors nodes/links by component.
- Clicking a node shows its name, position, interfaces/IPs, and routing table
  (or the documented empty text).
- Tracing a path marks the path edges and shows the chain/failure message.
- An over-cap topology shows the overflow message instead of freezing.
- Link titles include delay, capacity, loss, and jitter; the payload fields are
  present in API tests.

## Edge cases and error paths

- A satellite without shell metadata groups under `Unassigned`.
- A shell filter never hides ground stations unless the type filter does.
- No project: the page shows the no-project state and no graph.
- A failed path request clears prior highlighting and shows the error.
- Selecting a node that disappears on the next poll clears the inspector.
- The SVG uses textContent/title attributes, never unescaped innerHTML for
  topology values.
- The graph is capped before layout to bound work.

## Non-goals

- Timestamp history and added/removed-link comparison (phase 2).
- Force-directed/3D layouts, graph editing, or a new CDN graph library.
- Shell filtering for custom projects without shell metadata.
- Replacing World View or Node Explorer.

## Validation

- Backend/API tests for shell, loss, and jitter fields.
- Vitest for shell options, filter composition, layout determinism/bounds,
  partitions, and edge tooltips.
- Playwright with mocked nodes/links/detail/path for rendering, filters,
  partitions, path highlight, inspector, and empty/error states.
- Full pytest, Vitest, Playwright, Ruff, format, wheel build, and CI.
- Manual scale/legibility check at 1,000+ nodes reported.

## Decisions and open questions

- The ring layout groups satellites by shell and stations in the center; it is
  stable and dependency-free even if less organic than a force layout.
- Shell metadata comes from the simulation manager by object id because the
  topology satellite objects do not carry shells in default projects.
- Phase 2 will record snapshots on step changes rather than seeking the live
  simulation.
