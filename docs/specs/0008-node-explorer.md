# 0008 — Node Explorer search, filter, sort, and favorites

Status: accepted

## Context

The Nodes page renders every satellite and ground station and polls the list
every five seconds. A default project has hundreds of nodes, so finding one by
name or city requires scrolling the whole list. There is no count, filter, or
persistent way to watch a few nodes.

## Requirements

- Add a toolbar above the node cards with:
  - case-insensitive text search over name, city, and type;
  - type filter (all, satellites, ground stations);
  - sort by name (numeric-aware), city, or type;
  - a favorites-only filter;
  - a live "showing X of Y" count.
- Persist favorite node names in browser-local storage
  (`sgnt_node_favorites`), deduplicated and capped defensively.
- Add a per-row star toggle that does not expand the row.
- Keep the five-second poll from clobbering filters, sort order, or open
  details; a filter/sort change may rebuild the list.
- Hide the non-matching type card when a type filter is active; show an
  explicit per-card empty message when the filter has no matches.
- Pure filter/sort/favorite/normalization logic lives in `nodes_model.js` with
  Vitest coverage.

## Acceptance criteria

- Typing `berlin` matches a ground station by city; `SAT1` matches case-
  insensitively; clearing the search restores the list.
- Selecting a type hides the other card and updates the count.
- Sorting by name orders `Sat2` before `Sat10`; city sort puts stations with
  cities first and falls back to name for ties.
- Starring a node persists across reload; Favorites only leaves just starred
  nodes; unstarring removes it.
- The count reflects the filtered and total node counts.
- Existing row expansion, addressability toggle, path tracing, and polling
  still work.

## Edge cases and error paths

- Empty search and whitespace-only search are no-ops.
- Missing city/name/type values do not throw.
- Malformed favorites storage is ignored; unknown names are harmless.
- Filtering out an expanded node collapses/removes its detail; opening it again
  reloads from the detail cache or API.
- A poll during an open filter keeps the filter and detail state.
- No project or API failure keeps the existing message and clears both lists.

## Non-goals

- Server-side search or pagination.
- Saved filter presets or multi-select actions.
- Grouping by shell (the list remains split into satellite/ground-station
  cards).
- World View inspector changes; tracked separately.

## Validation

- Vitest for search matching, type filtering, favorites normalization/toggle,
  numeric/city sorting, counts, and empty inputs.
- Playwright for search, type filter, sort, favorite persistence, and the
  count with mocked nodes.
- Full pytest (page/static contracts), Vitest, Playwright, Ruff, format, wheel
  build, and CI.

## Decisions and open questions

- Filters operate on the full node list fetched by the existing poll; no
  backend change is needed.
- Favorites are names, not IDs, so they survive a project rebuild with the same
  naming scheme; missing names are simply ignored.
- The toolbar rebuilds the two lists on a filter/sort change to preserve order;
  polling keeps the incremental renderer.
