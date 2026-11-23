# 0009 — World View node inspector and link isolation

Status: accepted

## Context

World View can select a satellite (dimming its coverage circle) and shows a
Cesium InfoBox, but there is no accessible side panel summarizing the node's
position, incident links, or nearest peers. Link selection cannot be narrowed
to one node. Node Explorer has node details but no deep link back to the globe.

## Requirements

- Add an accessible DOM inspector panel on `/world` for a selected satellite or
  ground station: name, type, coordinates/altitude, incident link counts by
  category (GSL/orbital/adjacent), incident neighbors, and the nearest peers
  with great-circle distance.
- Add an "Isolate links" toggle that dims every link not incident to the
  selected node while it is enabled.
- Keep the existing Cesium click selection and coverage dimming; extend clicks
  to ground stations.
- Add an explicit close button that clears selection, coverage dimming, and
  link isolation.
- Support `/world?node=NAME` deep links; when data loads, select that node or
  show a visible not-found message.
- Add an "Open in World" link from the Node Explorer detail panel.
- Keep pure helpers in `world_model.js` with Vitest coverage.

## Acceptance criteria

- Selecting a satellite or ground station shows the panel with its name, type,
  formatted coordinates, link counts, neighbors, and up to five nearest peers.
- The isolate toggle visibly reduces non-incident link alpha; turning it off or
  closing the panel restores the normal link rendering.
- Clicking empty space clears the selection and panel.
- `/world?node=Sat12` opens with `Sat12` selected once satellite data arrives;
  an unknown name shows a not-found message without breaking the page.
- Node Explorer's detail panel links to `/world?node=<name>`.
- Null/missing positions are skipped in nearest-peer calculations and never
  throw.

## Edge cases and error paths

- A selected node that disappears on a later poll closes the panel.
- A node with no incident links shows a zero count and a "no incident links"
  message; isolation dims every link.
- Missing link types/directions fall back to the orbital category.
- The inspector must not rebuild its contents on every two-second poll unless
  the selection or data changed.
- WebGL fallback still hides the globe and shows the fallback; the panel is
  only created when Cesium initializes.
- Closing the panel during a path highlight preserves the path highlight.

## Non-goals

- 3D picking beyond the existing entity click behavior.
- Editing topology from the inspector.
- Shell metadata (not present in `/api/satellites`).
- Saved selections or multi-node isolation.

## Validation

- Vitest for link categorization/summaries, nearest-peer distance ordering,
  missing positions, and deep-link parsing.
- Playwright for the deep-link panel when WebGL is available in the test
  browser; otherwise the rendering path is reported as a manual check.
- Full pytest (page/static contracts), Vitest, Playwright, Ruff, format, wheel
  build, and CI.

## Decisions and open questions

- The inspector is a DOM region outside the Cesium canvas so it remains
  accessible and testable; Cesium's InfoBox stays untouched.
- Isolation is visual alpha reduction, not link removal, so paths and usage
  colors remain intact.
- Nearest peers use the haversine great-circle distance between node positions,
  not link distance.
